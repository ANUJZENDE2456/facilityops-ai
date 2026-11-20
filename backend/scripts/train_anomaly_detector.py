
#!/usr/bin/env python3
"""
Energy Anomaly Detection Engine - Training and Evaluation Script.

Loads 90-day historical telemetry from PostgreSQL, joins synthetic ground-truth
labels, trains per-meter Isolation Forest detectors on clean baseline data,
and evaluates performance on a chronological 30% test holdout.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import pandas as pd

# -----------------------------------------------------------------------------
# Path and Environment Setup
# -----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import SessionLocal  # noqa: E402
from app.ml import (  # noqa: E402
    FEATURE_COLUMNS,
    EnergyFeaturePipeline,
    MeterAnomalyDetector,
    calculate_metrics,
)
from app.models import EnergyReading, Facility  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("anomaly_training")

METERS = ["HVAC-01", "LIGHTING-01", "PLUG-LOAD-01", "MAIN-METER-01"]


# -----------------------------------------------------------------------------
# Data Ingestion & Ground-Truth Alignment
# -----------------------------------------------------------------------------
# Per-meter contamination, based on each meter's actual test anomaly rate
PER_METER_CONTAMINATION = {
    "HVAC-01": 0.05,
    "LIGHTING-01": 0.015,
    "PLUG-LOAD-01": 0.04,
    "MAIN-METER-01": 0.10,
}


def load_readings_from_db(facility_name: str) -> Tuple[Facility, pd.DataFrame]:
    """Load all energy readings for the given facility from PostgreSQL."""
    db = SessionLocal()

    try:
        facility = (
            db.query(Facility)
            .filter(Facility.name == facility_name)
            .first()
        )

        if not facility:
            raise ValueError(
                f"Facility '{facility_name}' not found. "
                "Run generate_energy_data.py first."
            )

        logger.info(
            f"Querying readings for '{facility.name}' (ID: {facility.id})..."
        )

        rows = (
            db.query(EnergyReading)
            .filter(EnergyReading.facility_id == facility.id)
            .order_by(
                EnergyReading.meter_id,
                EnergyReading.recorded_at.asc(),
            )
            .all()
        )

        if not rows:
            raise ValueError(
                f"No EnergyReading records found for facility ID {facility.id}."
            )

        data = [
            {
                "id": r.id,
                "facility_id": r.facility_id,
                "meter_id": r.meter_id,
                "power_kw": r.power_kw,
                "energy_kwh": r.energy_kwh,
                "voltage_v": r.voltage_v,
                "current_a": r.current_a,
                "recorded_at": r.recorded_at,
            }
            for r in rows
        ]

        df = pd.DataFrame(data)
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)

        logger.info(
            f"Loaded {len(df)} readings across "
            f"{df['meter_id'].nunique()} meters."
        )

        return facility, df

    finally:
        db.close()


def load_ground_truth(csv_path: str) -> pd.DataFrame:
    """Load ground-truth anomaly annotations from CSV."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Ground-truth CSV not found at: {csv_path}"
        )

    logger.info(f"Loading ground-truth labels from: {csv_path}")

    gt_df = pd.read_csv(csv_path)
    gt_df["timestamp"] = pd.to_datetime(gt_df["timestamp"], utc=True)

    logger.info(f"Loaded {len(gt_df)} ground-truth anomaly records.")

    return gt_df


def merge_readings_with_ground_truth(
    readings_df: pd.DataFrame,
    gt_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge database readings with ground-truth labels.
    Creates actual_anomaly: 1 = anomaly, 0 = normal.
    """
    df = readings_df.copy()
    gt = gt_df.copy()

    df["recorded_at_utc"] = pd.to_datetime(
        df["recorded_at"], utc=True
    )
    gt["timestamp_utc"] = pd.to_datetime(
        gt["timestamp"], utc=True
    )

    gt = gt.rename(
        columns={
            "timestamp_utc": "recorded_at_utc",
            "anomaly_label": "gt_anomaly_label",
            "severity": "gt_severity",
            "description": "gt_description",
        }
    )

    merged = pd.merge(
        df,
        gt[
            [
                "meter_id",
                "recorded_at_utc",
                "gt_anomaly_label",
                "gt_severity",
                "gt_description",
            ]
        ],
        on=["meter_id", "recorded_at_utc"],
        how="left",
        validate="one_to_one",
    )

    merged["actual_anomaly"] = (
        merged["gt_anomaly_label"].notna().astype(int)
    )

    merged = merged.drop(columns=["recorded_at_utc"])

    return merged


# -----------------------------------------------------------------------------
# Training and Evaluation Orchestration
# -----------------------------------------------------------------------------
def train_and_evaluate_meters(
    merged_df: pd.DataFrame,
    train_ratio: float = 0.70,
    contamination: Any = "auto",
    seed: int = 42,
) -> Tuple[
    Dict[str, MeterAnomalyDetector],
    pd.DataFrame,
    Dict[str, Any],
]:
    """
    Train one Isolation Forest per meter.

    Features are calculated on complete chronological meter history.
    Only clean training rows are used to fit the Isolation Forest.
    The final test period is excluded from model fitting.
    """
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio must be between 0 and 1.")

    models: Dict[str, MeterAnomalyDetector] = {}
    test_predictions_list: List[pd.DataFrame] = []
    metrics_per_meter: Dict[str, Any] = {}

    for meter_id in METERS:
        meter_data = (
            merged_df[merged_df["meter_id"] == meter_id]
            .sort_values("recorded_at")
            .reset_index(drop=True)
        )

        total_meter_readings = len(meter_data)

        if total_meter_readings == 0:
            logger.warning(
                f"No readings found for meter {meter_id}; skipping."
            )
            continue

        split_idx = int(total_meter_readings * train_ratio)

        if split_idx == 0 or split_idx == total_meter_readings:
            logger.warning(
                f"Insufficient readings for meter {meter_id}; skipping."
            )
            continue

        train_raw = meter_data.iloc[:split_idx].copy()
        test_raw = meter_data.iloc[split_idx:].copy()

        logger.info(
            f"Meter {meter_id}: Total={total_meter_readings} | "
            f"Train={len(train_raw)} | Test={len(test_raw)}"
        )

        # ---------------------------------------------------------------------
        # 1. Identify clean training rows
        # ---------------------------------------------------------------------
        anomalies_in_train = int(
            train_raw["actual_anomaly"].sum()
        )

        clean_train = train_raw[
            train_raw["actual_anomaly"] == 0
        ].copy()

        if clean_train.empty:
            logger.warning(
                f"No clean training readings for {meter_id}; skipping."
            )
            continue

        logger.info(
            f"Meter {meter_id}: Excluded {anomalies_in_train} "
            f"known training anomalies. "
            f"Clean baseline readings={len(clean_train)}."
        )

        # ---------------------------------------------------------------------
        # 2. Fit meter-specific expected consumption profile
        #    Only clean training data is used for this reference profile.
        # ---------------------------------------------------------------------
        pipeline = EnergyFeaturePipeline(
            feature_columns=FEATURE_COLUMNS
        )
        pipeline.fit(clean_train)

        # ---------------------------------------------------------------------
        # 3. Extract features on complete chronological history.
        #    This preserves hourly continuity for rolling calculations.
        # ---------------------------------------------------------------------
        all_features = pipeline.transform(meter_data)

        train_features_all = all_features.iloc[:split_idx]
        test_features = all_features.iloc[split_idx:]

        # Keep only clean rows when fitting Isolation Forest.
        clean_mask = (
            train_raw["actual_anomaly"] == 0
        ).to_numpy()

        train_features = (
            train_features_all.iloc[clean_mask]
            .reset_index(drop=True)
        )

        test_features = test_features.reset_index(drop=True)

        if train_features.empty or test_features.empty:
            logger.warning(
                f"Empty feature set for {meter_id}; skipping."
            )
            continue

        # ---------------------------------------------------------------------
        # 4. Train dedicated Isolation Forest
        # ---------------------------------------------------------------------
        detector = MeterAnomalyDetector(
            meter_id=meter_id,
            contamination=(
                contamination.get(meter_id, "auto")
                if isinstance(contamination, dict)
                else contamination
            ),
            n_estimators=150,
            random_state=seed,
        )

        detector.fit(train_features)

        # Preserve the fitted feature pipeline inside the saved detector.
        detector.pipeline = pipeline

        models[meter_id] = detector

        # ---------------------------------------------------------------------
        # 5. Evaluate on final 30% test set
        # ---------------------------------------------------------------------
        preds = detector.predict(test_features)
        scores = detector.score_samples(test_features)

        severities = [
            detector.map_severity(score, prediction)
            for score, prediction in zip(scores, preds)
        ]

        test_evaluated = test_raw.copy()
        test_evaluated["predicted_anomaly"] = preds
        test_evaluated["anomaly_score"] = scores
        test_evaluated["severity"] = severities

        test_predictions_list.append(test_evaluated)

        # ---------------------------------------------------------------------
        # 6. Calculate per-meter metrics
        # ---------------------------------------------------------------------
        meter_metrics = calculate_metrics(
            y_true=test_evaluated["actual_anomaly"].values,
            y_pred=test_evaluated["predicted_anomaly"].values,
        )

        meter_metrics["clean_training_samples"] = len(clean_train)
        meter_metrics["excluded_train_anomalies"] = anomalies_in_train
        meter_metrics["test_samples"] = len(test_raw)

        metrics_per_meter[meter_id] = meter_metrics

        logger.info(
            f"Meter {meter_id}: "
            f"Precision={meter_metrics['precision']:.4f}, "
            f"Recall={meter_metrics['recall']:.4f}, "
            f"F1={meter_metrics['f1_score']:.4f}"
        )

    # -------------------------------------------------------------------------
    # Combine predictions and calculate overall metrics
    # -------------------------------------------------------------------------
    if not test_predictions_list:
        raise RuntimeError(
            "No meter models were trained. Check the input data."
        )

    all_test_predictions = pd.concat(
        test_predictions_list,
        ignore_index=True,
    )

    overall_metrics = calculate_metrics(
        y_true=all_test_predictions["actual_anomaly"].values,
        y_pred=all_test_predictions["predicted_anomaly"].values,
    )

    evaluation_report = {
        "metadata": {
            "evaluation_timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "train_ratio": train_ratio,
            "test_ratio": round(1.0 - train_ratio, 2),
            "contamination_param": str(contamination),
            "features_used": FEATURE_COLUMNS,
            "feature_count": len(FEATURE_COLUMNS),
            "feature_method": (
                "Per-meter training-fitted expected profile and rolling "
                "features calculated over complete chronological history."
            ),
            "clean_training_assumption": (
                "Known synthetic anomalies were excluded from Isolation "
                "Forest fitting. Feature extraction retained chronological "
                "continuity. The final test period was not used to fit "
                "the model or expected consumption profile."
            ),
            "synthetic_evaluation_limitations": [
                (
                    "Synthetic patterns follow parameterized sinusoidal "
                    "and operational templates which exhibit higher "
                    "regularity than real-world facilities."
                ),
                (
                    "Real facilities introduce sensor drift, weather "
                    "extremes, equipment degradation, and occupant "
                    "behavior that may increase false positives."
                ),
                (
                    "Synthetic evaluation results do not guarantee "
                    "equivalent production performance. Real deployments "
                    "require human review and ongoing validation."
                ),
            ],
        },
        "overall": overall_metrics,
        "per_meter": metrics_per_meter,
    }

    return models, all_test_predictions, evaluation_report


# -----------------------------------------------------------------------------
# Persistence and Reporting
# -----------------------------------------------------------------------------
def save_artifacts(
    models: Dict[str, MeterAnomalyDetector],
    test_predictions: pd.DataFrame,
    evaluation_report: Dict[str, Any],
    artifacts_dir: str,
) -> Dict[str, str]:
    """Save trained models, metrics, and test predictions."""
    os.makedirs(artifacts_dir, exist_ok=True)

    saved_paths: Dict[str, str] = {}

    # 1. Save models
    for meter_id, model in models.items():
        model_path = os.path.join(
            artifacts_dir,
            f"model_{meter_id}.joblib",
        )

        model.save(model_path)
        saved_paths[f"model_{meter_id}"] = model_path

        logger.info(
            f"Saved model for {meter_id} -> {model_path}"
        )

    # 2. Save evaluation metrics
    metrics_path = os.path.join(
        artifacts_dir,
        "evaluation_metrics.json",
    )

    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(evaluation_report, f, indent=2)

    saved_paths["evaluation_metrics"] = metrics_path

    # 3. Save test predictions
    output_cols = [
        "facility_id",
        "meter_id",
        "recorded_at",
        "actual_anomaly",
        "predicted_anomaly",
        "anomaly_score",
        "severity",
    ]

    preds_csv_path = os.path.join(
        artifacts_dir,
        "test_predictions.csv",
    )

    test_predictions[output_cols].to_csv(
        preds_csv_path,
        index=False,
    )

    saved_paths["test_predictions"] = preds_csv_path

    logger.info(
        f"Saved {len(test_predictions)} test predictions."
    )

    return saved_paths


def print_evaluation_summary(
    evaluation_report: Dict[str, Any],
    saved_paths: Dict[str, str],
) -> None:
    """Print structured evaluation summary."""
    overall = evaluation_report["overall"]
    cm = overall["confusion_matrix"]
    per_meter = evaluation_report["per_meter"]

    recall = overall["recall"]
    f1_score = overall["f1_score"]

    recall_str = (
        f"{recall * 100:.2f}%"
        if recall is not None
        else "N/A"
    )

    f1_str = (
        f"{f1_score * 100:.2f}%"
        if f1_score is not None
        else "N/A"
    )

    feature_count = evaluation_report["metadata"]["feature_count"]

    print("\n" + "=" * 88)
    print(
        "Agentic FacilityOps AI Platform - "
        "Energy Anomaly Detection Evaluation"
    )
    print("=" * 88)

    print(
        f"Evaluation Timestamp: "
        f"{evaluation_report['metadata']['evaluation_timestamp']}"
    )
    print(f"Features Employed ({feature_count}):")
    print(", ".join(FEATURE_COLUMNS))
    print("Train/Test Split: 70% Historical Train / 30% Future Holdout")

    print("-" * 88)
    print("OVERALL TEST METRICS:")

    print(f"  Total Test Samples:  {overall['total_samples']:,}")
    print(f"  Actual Normals:      {overall['actual_normals']:,}")
    print(f"  Actual Anomalies:    {overall['actual_anomalies']:,}")
    print(f"  Predicted Anomalies: {overall['predicted_anomalies']:,}")

    print("  Confusion Matrix:")
    print(f"    True Positives (TP):  {cm['true_positives']:>5}")
    print(f"    False Positives (FP): {cm['false_positives']:>5}")
    print(f"    True Negatives (TN):  {cm['true_negatives']:>5}")
    print(f"    False Negatives (FN): {cm['false_negatives']:>5}")

    print(f"  Accuracy:  {overall['accuracy'] * 100:.2f}%")
    print(f"  Precision: {overall['precision'] * 100:.2f}%")
    print(f"  Recall:    {recall_str}")
    print(f"  F1-Score:  {f1_str}")

    print("-" * 88)
    print("PER-METER PERFORMANCE:")

    header = (
        f"{'Meter ID':<15} | {'Samples':>7} | {'Act Anom':>8} | "
        f"{'Pred Anom':>9} | {'TP':>4} | {'FP':>4} | "
        f"{'TN':>4} | {'FN':>4} | {'Prec %':>8} | "
        f"{'Recall %':>8} | {'F1 %':>7}"
    )

    print(header)
    print("-" * len(header))

    for meter_id, metrics in per_meter.items():
        matrix = metrics["confusion_matrix"]

        precision = metrics["precision"]
        recall = metrics["recall"]
        f1 = metrics["f1_score"]

        print(
            f"{meter_id:<15} | "
            f"{metrics['total_samples']:>7} | "
            f"{metrics['actual_anomalies']:>8} | "
            f"{metrics['predicted_anomalies']:>9} | "
            f"{matrix['true_positives']:>4} | "
            f"{matrix['false_positives']:>4} | "
            f"{matrix['true_negatives']:>4} | "
            f"{matrix['false_negatives']:>4} | "
            f"{precision * 100:>7.2f}% | "
            f"{recall * 100:>7.2f}% | "
            f"{f1 * 100:>6.2f}%"
        )

    print("-" * 88)
    print("METRIC INTERPRETATION:")
    print(
        "  Accuracy measures total correctness and can be misleading "
        "with imbalanced data."
    )
    print(
        "  Precision measures how many flagged readings were actual anomalies."
    )
    print(
        "  Recall measures how many actual anomalies were detected."
    )
    print(
        "  F1-score balances precision and recall."
    )

    print("-" * 88)
    print("METHODOLOGICAL LIMITATIONS:")

    for index, limitation in enumerate(
        evaluation_report["metadata"][
            "synthetic_evaluation_limitations"
        ],
        1,
    ):
        print(f"  [{index}] {limitation}")

    print("-" * 88)
    print("GENERATED ARTIFACTS:")

    for key, path in saved_paths.items():
        print(f"  {key:<22}: {path}")

    print("=" * 88 + "\n")


# -----------------------------------------------------------------------------
# CLI Entrypoint
# -----------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Train per-meter Isolation Forest anomaly detectors "
            "and evaluate performance."
        )
    )

    parser.add_argument(
        "--facility-name",
        type=str,
        default="Demo Corporate Office",
    )

    parser.add_argument(
        "--csv-path",
        type=str,
        default=os.path.join(
            BACKEND_DIR,
            "data",
            "anomaly_ground_truth.csv",
        ),
    )

    parser.add_argument(
        "--artifacts-dir",
        type=str,
        default=os.path.join(
            BACKEND_DIR,
            "artifacts",
        ),
    )

    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.70,
    )

    parser.add_argument(
        "--contamination",
        type=str,
        default="auto",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    parser.add_argument(
        "--per-meter",
        action="store_true",
        help="Use per-meter contamination values",
    )

    args = parser.parse_args()

    try:
        contamination_val: Any = float(args.contamination)
    except ValueError:
        contamination_val = args.contamination

    if args.per_meter:
        contamination_val = PER_METER_CONTAMINATION

    logger.info(
        "Initializing Energy Anomaly Detection Training Engine..."
    )
    logger.info(
        f"Target Facility: '{args.facility_name}' | "
        f"Train Split: {args.train_ratio * 100:.0f}%"
    )

    # 1. Load database readings
    facility, readings_df = load_readings_from_db(
        facility_name=args.facility_name
    )

    # 2. Load ground-truth labels
    gt_df = load_ground_truth(
        csv_path=args.csv_path
    )

    # 3. Merge readings and labels
    merged_df = merge_readings_with_ground_truth(
        readings_df,
        gt_df,
    )

    # 4. Train and evaluate
    models, test_predictions, evaluation_report = (
        train_and_evaluate_meters(
            merged_df=merged_df,
            train_ratio=args.train_ratio,
            contamination=contamination_val,
            seed=args.seed,
        )
    )

    # 5. Save artifacts
    saved_paths = save_artifacts(
        models=models,
        test_predictions=test_predictions,
        evaluation_report=evaluation_report,
        artifacts_dir=args.artifacts_dir,
    )

    # 6. Print evaluation
    print_evaluation_summary(
        evaluation_report,
        saved_paths,
    )


if __name__ == "__main__":
    main()

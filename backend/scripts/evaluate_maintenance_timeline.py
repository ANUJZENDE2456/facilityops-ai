
import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.database.session import SessionLocal
from app.ml.maintenance_health import calculate_health_score
from app.models import Asset, AssetReading


GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "maintenance_ground_truth.csv"
)

HEALTH_THRESHOLD = 85
BASELINE_READINGS = 168
CHECKPOINT_DAYS = [0, 7, 14, 21, 28]


def parse_datetime(value):
    timestamp = datetime.fromisoformat(value)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


def normalize_datetime(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def load_ground_truth():
    records = []

    with GROUND_TRUTH_PATH.open(
        "r", newline="", encoding="utf-8"
    ) as file:
        for row in csv.DictReader(file):
            records.append({
                "facility_id": int(row["facility_id"]),
                "asset_code": row["asset_code"],
                "state": row["state"].upper(),
                "degradation_start": parse_datetime(
                    row["degradation_start"]
                ),
                "failure_time": (
                    parse_datetime(row["failure_time"])
                    if row["failure_time"] else None
                ),
            })

    return records


def calculate_baseline(readings):
    baseline_readings = readings[:BASELINE_READINGS]

    if len(baseline_readings) < 5:
        return None

    def average(field):
        values = [
            getattr(reading, field)
            for reading in baseline_readings
            if getattr(reading, field) is not None
        ]

        return sum(values) / len(values) if values else 0.0

    baseline = {
        "temperature": average("temperature_c"),
        "vibration": average("vibration_mm_s"),
        "current": average("current_a"),
    }

    if min(baseline.values()) <= 0:
        return None

    return baseline


def evaluate_at_checkpoint(readings, baseline, checkpoint):
    # Never use a reading recorded after the checkpoint.
    available = [
        reading
        for reading in readings
        if normalize_datetime(reading.recorded_at) <= checkpoint
    ]

    if not available:
        return None

    latest = available[-1]

    result = calculate_health_score(
        temperature_c=latest.temperature_c or 0.0,
        vibration_mm_s=latest.vibration_mm_s or 0.0,
        current_a=latest.current_a or 0.0,
        baseline_temperature=baseline["temperature"],
        baseline_vibration=baseline["vibration"],
        baseline_current=baseline["current"],
    )

    return {
        "score": result.health_score,
        "condition": result.condition,
        "reading_time": normalize_datetime(
            latest.recorded_at
        ),
        "prediction": result.health_score < HEALTH_THRESHOLD,
    }


def calculate_metrics(rows, threshold):
    tp = fp = tn = fn = 0

    for row in rows:
        actual = row["actual_positive"]
        predicted = row["score"] < threshold

        if actual and predicted:
            tp += 1
        elif not actual and predicted:
            fp += 1
        elif not actual and not predicted:
            tn += 1
        else:
            fn += 1

    total = tp + fp + tn + fn

    accuracy = (tp + tn) / total if total else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0

    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0
    )

    return tp, fp, tn, fn, accuracy, precision, recall, f1
def main():
    ground_truth = load_ground_truth()

    db = SessionLocal()

    try:
        assets = db.scalars(
            select(Asset).order_by(
                Asset.facility_id,
                Asset.asset_code,
            )
        ).all()

        asset_lookup = {
            (asset.facility_id, asset.asset_code): asset
            for asset in assets
        }

        abnormal_by_facility = defaultdict(list)

        for record in ground_truth:
            abnormal_by_facility[
                record["facility_id"]
            ].append(record)

        results = []
        skipped = 0

        # Evaluate abnormal assets at historical checkpoints.
        for record in ground_truth:
            key = (
                record["facility_id"],
                record["asset_code"],
            )

            asset = asset_lookup.get(key)

            if not asset:
                print(f"[SKIP] Asset not found: {key}")
                skipped += 1
                continue

            readings = db.scalars(
                select(AssetReading)
                .where(AssetReading.asset_id == asset.id)
                .order_by(AssetReading.recorded_at.asc())
            ).all()

            baseline = calculate_baseline(readings)

            if baseline is None:
                print(f"[SKIP] Insufficient baseline: {key}")
                skipped += 1
                continue

            for days in CHECKPOINT_DAYS:
                checkpoint = (
                    record["degradation_start"]
                    + timedelta(days=days)
                )

                if (
                    record["failure_time"]
                    and checkpoint >= record["failure_time"]
                ):
                    continue

                evaluation = evaluate_at_checkpoint(
                    readings,
                    baseline,
                    checkpoint,
                )

                if evaluation is None:
                    continue

                results.append({
                    "facility": record["facility_id"],
                    "asset": record["asset_code"],
                    "actual_state": record["state"],
                    "checkpoint": checkpoint,
                    "score": evaluation["score"],
                    "condition": evaluation["condition"],
                    "actual_positive": True,
                    "predicted_positive": evaluation["prediction"],
                })

        # Evaluate healthy assets at the same facility's
        # abnormal-asset checkpoint dates.
        for facility_id, records in abnormal_by_facility.items():
            checkpoints = set()

            for record in records:
                for days in CHECKPOINT_DAYS:
                    checkpoint = (
                        record["degradation_start"]
                        + timedelta(days=days)
                    )

                    if (
                        record["failure_time"]
                        and checkpoint >= record["failure_time"]
                    ):
                        continue

                    checkpoints.add(checkpoint)

            healthy_assets = [
                asset for asset in assets
                if asset.facility_id == facility_id
                and (
                    facility_id,
                    asset.asset_code,
                ) not in {
                    (r["facility_id"], r["asset_code"])
                    for r in ground_truth
                }
            ]

            for asset in healthy_assets:
                readings = db.scalars(
                    select(AssetReading)
                    .where(AssetReading.asset_id == asset.id)
                    .order_by(AssetReading.recorded_at.asc())
                ).all()

                baseline = calculate_baseline(readings)

                if baseline is None:
                    skipped += 1
                    continue

                for checkpoint in sorted(checkpoints):
                    evaluation = evaluate_at_checkpoint(
                        readings,
                        baseline,
                        checkpoint,
                    )

                    if evaluation is None:
                        continue

                    results.append({
                        "facility": facility_id,
                        "asset": asset.asset_code,
                        "actual_state": "HEALTHY",
                        "checkpoint": checkpoint,
                        "score": evaluation["score"],
                        "condition": evaluation["condition"],
                        "actual_positive": False,
                        "predicted_positive": evaluation["prediction"],
                    })

        print("\n========== TIME-AWARE MAINTENANCE EVALUATION ==========\n")

        for row in results:
            print(
                f"Facility {row['facility']} | "
                f"{row['asset']:12} | "
                f"{row['checkpoint'].strftime('%Y-%m-%d')} | "
                f"Actual: {row['actual_state']:9} | "
                f"Score: {row['score']:6.2f} | "
                f"{'ALERT' if row['predicted_positive'] else 'HEALTHY'}"
            )


        print("\n========== THRESHOLD SENSITIVITY ANALYSIS ==========\n")

        print(
            f"{'Threshold':<12}"
            f"{'TP':<8}"
            f"{'FP':<8}"
            f"{'TN':<8}"
            f"{'FN':<8}"
            f"{'Accuracy':<12}"
            f"{'Precision':<12}"
            f"{'Recall':<12}"
            f"{'F1':<12}"
        )

        for threshold in [70, 75, 80, 85, 90]:
            tp, fp, tn, fn, accuracy, precision, recall, f1 = (
                calculate_metrics(results, threshold)
            )

            print(
                f"{threshold:<12}"
                f"{tp:<8}"
                f"{fp:<8}"
                f"{tn:<8}"
                f"{fn:<8}"
                f"{accuracy * 100:<12.2f}"
                f"{precision * 100:<12.2f}"
                f"{recall * 100:<12.2f}"
                f"{f1 * 100:<12.2f}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()

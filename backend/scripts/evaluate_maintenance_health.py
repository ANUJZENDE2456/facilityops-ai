
import csv
from pathlib import Path

from app.database import SessionLocal
from app.models import Asset
from app.agents.maintenance_agent import MaintenanceAgent


GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "maintenance_ground_truth.csv"
)

# Health score below 85 means the asset is not classified as HEALTHY.
HEALTH_THRESHOLD = 85


def load_ground_truth():
    ground_truth = {}

    with open(GROUND_TRUTH_PATH, "r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            key = (int(row["facility_id"]), row["asset_code"])
            ground_truth[key] = row["state"].upper()

    return ground_truth


def calculate_metrics(tp, fp, tn, fn):
    total = tp + fp + tn + fn

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0
    )
    accuracy = (tp + tn) / total if total else 0

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main():
    ground_truth = load_ground_truth()

    db = SessionLocal()

    try:
        agent = MaintenanceAgent(db)

        assets = db.query(Asset).order_by(
            Asset.facility_id,
            Asset.asset_code,
        ).all()

        tp = fp = tn = fn = 0
        results = []

        for asset in assets:
            key = (asset.facility_id, asset.asset_code)

            # Assets absent from the ground-truth file are healthy.
            actual_state = ground_truth.get(key, "HEALTHY")

            actual_positive = actual_state in {
                "DEGRADING",
                "FAILED",
            }

            analysis = agent.analyze_asset(asset.id)

            if "health_score" not in analysis:
                print(
                    f"Skipping {asset.asset_code}: "
                    f"{analysis.get('error', 'Analysis unavailable')}"
                )
                continue

            score = analysis["health_score"]

            predicted_positive = score < HEALTH_THRESHOLD

            if actual_positive and predicted_positive:
                tp += 1
                prediction = "CORRECT ALERT"

            elif not actual_positive and predicted_positive:
                fp += 1
                prediction = "FALSE ALERT"

            elif actual_positive and not predicted_positive:
                fn += 1
                prediction = "MISSED"

            else:
                tn += 1
                prediction = "CORRECT HEALTHY"

            results.append({
                "facility": asset.facility_id,
                "asset": asset.asset_code,
                "actual": actual_state,
                "health_score": score,
                "predicted": (
                    "DEGRADING/FAILED"
                    if predicted_positive else "HEALTHY"
                ),
                "result": prediction,
            })

        print("\n========== MAINTENANCE MODEL EVALUATION ==========\n")

        for item in results:
            print(
                f"Facility {item['facility']} | "
                f"{item['asset']:12} | "
                f"Actual: {item['actual']:9} | "
                f"Score: {item['health_score']:6.2f} | "
                f"Prediction: {item['predicted']:15} | "
                f"{item['result']}"
            )

        metrics = calculate_metrics(tp, fp, tn, fn)

        print("\n================ CONFUSION MATRIX ================\n")
        print(f"True Positives  (TP): {tp}")
        print(f"False Positives (FP): {fp}")
        print(f"True Negatives  (TN): {tn}")
        print(f"False Negatives (FN): {fn}")

        print("\n================ PERFORMANCE METRICS =============\n")
        print(f"Total evaluated: {len(results)}")
        print(f"Accuracy:  {metrics['accuracy']:.2%}")
        print(f"Precision: {metrics['precision']:.2%}")
        print(f"Recall:    {metrics['recall']:.2%}")
        print(f"F1 Score:  {metrics['f1']:.2%}")

        print("\n===================================================\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()

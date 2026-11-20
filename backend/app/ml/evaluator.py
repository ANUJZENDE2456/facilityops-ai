"""
Evaluation and Metrics Computation for Anomaly Detection.

Computes accuracy, precision, recall, F1-score, and confusion matrices
per meter and overall platform aggregation.
"""

from __future__ import annotations

from typing import Any, Dict, List
import numpy as np


def calculate_metrics(
    y_true: List[int] | np.ndarray,
    y_pred: List[int] | np.ndarray,
) -> Dict[str, Any]:
    """
    Computes classification evaluation metrics for binary anomaly predictions.

    Args:
        y_true: Ground truth binary labels (0 = normal, 1 = anomaly).
        y_pred: Predicted binary labels (0 = normal, 1 = anomaly).

    Returns:
        Dictionary containing counts, confusion matrix, and performance metrics.
    """
    y_t = np.asarray(y_true, dtype=int)
    y_p = np.asarray(y_pred, dtype=int)

    total_samples = int(len(y_t))
    if total_samples == 0:
        return {
            "total_samples": 0,
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1_score": 0.0,
            "confusion_matrix": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
        }

    tp = int(np.sum((y_t == 1) & (y_p == 1)))
    fp = int(np.sum((y_t == 0) & (y_p == 1)))
    tn = int(np.sum((y_t == 0) & (y_p == 0)))
    fn = int(np.sum((y_t == 1) & (y_p == 0)))

    actual_anomalies = int(np.sum(y_t == 1))
    actual_normals = int(np.sum(y_t == 0))
    predicted_anomalies = int(np.sum(y_p == 1))

    # Accuracy: (TP + TN) / Total
    accuracy = (tp + tn) / total_samples

    # Precision: TP / (TP + FP)
    if (tp + fp) > 0:
        precision = tp / (tp + fp)
    else:
        precision = 1.0 if actual_anomalies == 0 else 0.0

    # Recall: TP / (TP + FN)
    if actual_anomalies > 0:
        recall = tp / actual_anomalies
    else:
        # If a meter has zero actual positive samples, recall is mathematically undefined (N/A)
        recall = None

    # Precision: TP / (TP + FP)
    if (tp + fp) > 0:
        precision = tp / (tp + fp)
    else:
        precision = 1.0 if actual_anomalies == 0 else 0.0

    # F1-Score: 2 * (Precision * Recall) / (Precision + Recall)
    if recall is not None:
        if (precision + recall) > 0:
            f1_score = 2.0 * (precision * recall) / (precision + recall)
        else:
            f1_score = 0.0
    else:
        f1_score = None

    return {
        "total_samples": total_samples,
        "actual_normals": actual_normals,
        "actual_anomalies": actual_anomalies,
        "predicted_anomalies": predicted_anomalies,
        "confusion_matrix": {
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
        },
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4) if recall is not None else None,
        "f1_score": round(float(f1_score), 4) if f1_score is not None else None,
    }

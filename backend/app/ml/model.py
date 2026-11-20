"""
Isolation Forest Anomaly Detection Model for Energy Telemetry.

Encapsulates meter-specific IsolationForest models, score calibration,
severity categorization, and joblib serialization.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.ml.features import FEATURE_COLUMNS, EnergyFeaturePipeline


class MeterAnomalyDetector:
    """
    Dedicated anomaly detector for an individual energy meter using Isolation Forest.
    """

    def __init__(
        self,
        meter_id: str,
        contamination: Union[float, str] = "auto",
        n_estimators: int = 150,
        random_state: int = 42,
    ):
        self.meter_id = meter_id
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state

        self.pipeline = EnergyFeaturePipeline(feature_columns=FEATURE_COLUMNS)
        self.model: Optional[IsolationForest] = None
        self.trained_at: Optional[datetime] = None
        self.n_samples_trained: int = 0
        self.training_columns: List[str] = FEATURE_COLUMNS

    def fit(self, X: pd.DataFrame) -> MeterAnomalyDetector:
        """
        Trains the IsolationForest on clean baseline telemetry features.

        Args:
            X: Feature matrix DataFrame matching FEATURE_COLUMNS.
        """
        if X.empty:
            raise ValueError(f"Cannot train detector for meter {self.meter_id} on empty feature matrix.")

        self.model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.model.fit(X[self.training_columns])
        self.trained_at = datetime.now(timezone.utc)
        self.n_samples_trained = len(X)
        return self

    def score_samples(self, X: pd.DataFrame) -> np.ndarray:
        """
        Computes calibrated continuous anomaly scores in range [0.0, 1.0].
        Higher values indicate higher likelihood and severity of anomaly.
        """
        if self.model is None:
            raise RuntimeError(f"Detector for meter {self.meter_id} has not been trained yet.")

        # decision_function: positive for inliers, negative for outliers
        dec_func = self.model.decision_function(X[self.training_columns])

        # Smooth sigmoid mapping centered on the decision boundary d=0.0 -> score=0.5
        scores = 1.0 / (1.0 + np.exp(dec_func * 8.0))
        return np.round(scores, 4)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predicts binary anomaly labels:
        1 = Anomaly (outlier)
        0 = Normal (inlier)
        """
        if self.model is None:
            raise RuntimeError(f"Detector for meter {self.meter_id} has not been trained yet.")

        raw_preds = self.model.predict(X[self.training_columns])
        # Scikit-learn outputs: -1 for outlier, +1 for inlier
        return np.where(raw_preds == -1, 1, 0)

    @staticmethod
    def map_severity(score: float, is_anomaly: int) -> str:
        """
        Maps continuous anomaly score and binary flag to categorical severity level.
        """
        if is_anomaly == 0:
            return "NORMAL"
        if score >= 0.85:
            return "CRITICAL"
        if score >= 0.70:
            return "HIGH"
        if score >= 0.55:
            return "MEDIUM"
        return "LOW"

    def evaluate_readings(
        self,
        readings_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Runs feature extraction, scoring, prediction, and severity mapping
        for a DataFrame of readings.

        Args:
            readings_df: DataFrame containing at least 'recorded_at', 'power_kw'.

        Returns:
            DataFrame with 'predicted_anomaly', 'anomaly_score', and 'severity'.
        """
        features_df = self.pipeline.transform(readings_df)
        preds = self.predict(features_df)
        scores = self.score_samples(features_df)

        severities = [
            self.map_severity(score, pred)
            for score, pred in zip(scores, preds)
        ]

        result = readings_df.copy()
        result["predicted_anomaly"] = preds
        result["anomaly_score"] = scores
        result["severity"] = severities
        return result

    def save(self, filepath: str) -> None:
        """Saves trained detector to disk via joblib."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        joblib.dump(self, filepath)

    @staticmethod
    def load(filepath: str) -> MeterAnomalyDetector:
        """Loads a saved detector from disk."""
        return joblib.load(filepath)

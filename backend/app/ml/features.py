
from __future__ import annotations

import math
from typing import List

import numpy as np
import pandas as pd

FEATURE_COLUMNS: List[str] = [
    "power_kw",
    "hour_sin",
    "hour_cos",
    "day_sin",
    "day_cos",
    "is_weekend",
    "rolling_mean_6h",
    "rolling_std_6h",
    "rolling_mean_24h",
    "power_ratio_24h",
    "rolling_mean_72h",
    "power_ratio_72h",
    "expected_power_kw",
    "residual_from_expected",
    "power_diff_1h",
]


class EnergyFeaturePipeline:
    """Causal feature engineering pipeline for energy telemetry."""

    def __init__(self, feature_columns: List[str] = FEATURE_COLUMNS):
        self.feature_columns = feature_columns
        self.expected_profile = {}
        self.global_median = None
        self.is_fitted = False

    def fit(self, clean_training_df: pd.DataFrame):
        """
        Fit expected consumption using clean training observations only.
        """
        if clean_training_df.empty:
            raise ValueError("Cannot fit feature pipeline on empty training data.")

        data = clean_training_df.copy()
        data["recorded_at"] = pd.to_datetime(
            data["recorded_at"], utc=True
        )
        data = data.sort_values("recorded_at")

        hours = data["recorded_at"].dt.hour
        weekends = (data["recorded_at"].dt.weekday >= 5).astype(int)

        data["_hour"] = hours
        data["_weekend"] = weekends

        self.global_median = float(data["power_kw"].median())

        self.expected_profile = (
            data.groupby(["_hour", "_weekend"])["power_kw"]
            .mean()
            .to_dict()
        )

        self.is_fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate features using current and historical readings only.
        """
        if df.empty:
            return pd.DataFrame(columns=self.feature_columns)

        if not self.is_fitted:
            raise RuntimeError(
                "Feature pipeline is not fitted. Call fit() first."
            )

        data = df.copy()

        data["recorded_at"] = pd.to_datetime(
            data["recorded_at"], utc=True
        )

        data = data.sort_values("recorded_at").reset_index(drop=True)

        power = data["power_kw"].astype(float)
        dt = data["recorded_at"].dt

        # Calendar features
        hours = dt.hour
        weekdays = dt.weekday

        hour_rad = 2.0 * math.pi * hours / 24.0
        day_rad = 2.0 * math.pi * weekdays / 7.0

        data["hour_sin"] = np.sin(hour_rad)
        data["hour_cos"] = np.cos(hour_rad)
        data["day_sin"] = np.sin(day_rad)
        data["day_cos"] = np.cos(day_rad)
        data["is_weekend"] = (weekdays >= 5).astype(int)

        # Causal rolling features
        lagged_power = power.shift(1).fillna(power)

        roll_6 = lagged_power.rolling(window=6, min_periods=1)
        data["rolling_mean_6h"] = roll_6.mean()
        data["rolling_std_6h"] = roll_6.std().fillna(0.0)

        roll_24 = lagged_power.rolling(window=24, min_periods=1)
        data["rolling_mean_24h"] = roll_24.mean()
        data["power_ratio_24h"] = (
            power / (data["rolling_mean_24h"] + 1e-4)
        )

        roll_72 = lagged_power.rolling(window=72, min_periods=6)
        data["rolling_mean_72h"] = (
            roll_72.mean().fillna(data["rolling_mean_24h"])
        )
        data["power_ratio_72h"] = (
            power / (data["rolling_mean_72h"] + 1e-4)
        )

        # Training-only expected consumption profile
        expected = [
            self.expected_profile.get(
                (int(hour), int(weekend)),
                self.global_median,
            )
            for hour, weekend in zip(hours, data["is_weekend"])
        ]

        data["expected_power_kw"] = expected
        data["residual_from_expected"] = (
            power - data["expected_power_kw"]
        )

        # Previous-hour rate of change
        data["power_diff_1h"] = power.diff().fillna(0.0)

        return data[self.feature_columns]

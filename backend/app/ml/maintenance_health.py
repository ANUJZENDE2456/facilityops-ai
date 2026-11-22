
from dataclasses import dataclass


@dataclass
class HealthResult:
    health_score: float
    condition: str
    risk_level: str
    recommendations: list[str]


def calculate_health_score(
    temperature_c: float,
    vibration_mm_s: float,
    current_a: float,
    baseline_temperature: float,
    baseline_vibration: float,
    baseline_current: float,
) -> HealthResult:
    """
    Calculate equipment health from deviations against
    its normal operating baseline.
    """

    def deviation(value, baseline):
        if baseline <= 0:
            return 0.0
        return max(0.0, (value - baseline) / baseline)

    temp_deviation = deviation(
        temperature_c, baseline_temperature
    )
    vibration_deviation = deviation(
        vibration_mm_s, baseline_vibration
    )
    current_deviation = deviation(
        current_a, baseline_current
    )

    # Weighted risk score.
    risk_score = (
        min(temp_deviation, 1.0) * 30
        + min(vibration_deviation, 1.0) * 45
        + min(current_deviation, 1.0) * 25
    )

    health_score = round(max(0.0, 100.0 - risk_score), 2)

    if health_score >= 85:
        condition = "HEALTHY"
        risk_level = "LOW"
    elif health_score >= 70:
        condition = "GOOD"
        risk_level = "LOW"
    elif health_score >= 50:
        condition = "DEGRADING"
        risk_level = "MEDIUM"
    elif health_score >= 30:
        condition = "POOR"
        risk_level = "HIGH"
    else:
        condition = "CRITICAL"
        risk_level = "CRITICAL"

    recommendations = []

    if temp_deviation > 0.15:
        recommendations.append(
            "Inspect cooling system and temperature control."
        )

    if vibration_deviation > 0.15:
        recommendations.append(
            "Inspect bearings, alignment, and mechanical vibration."
        )

    if current_deviation > 0.15:
        recommendations.append(
            "Inspect motor load and electrical connections."
        )

    if not recommendations:
        recommendations.append(
            "Continue routine equipment monitoring."
        )

    return HealthResult(
        health_score=health_score,
        condition=condition,
        risk_level=risk_level,
        recommendations=recommendations,
    )

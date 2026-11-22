
from datetime import date, datetime, timezone, timedelta

from sqlalchemy import func, select

from app.ml.maintenance_health import calculate_health_score
from app.models import Asset, AssetReading, MaintenanceRecord

class MaintenanceAgent:

    def __init__(self, db):
        self.db = db
    def get_asset_lifecycle(self, asset: Asset):
        today = date.today()

        # Count all maintenance records for this asset.
        maintenance_history_count = self.db.scalar(
            select(func.count(MaintenanceRecord.id))
            .where(MaintenanceRecord.asset_id == asset.id)
        ) or 0

        # Find the most recent completed maintenance.
        last_completed_date = self.db.scalar(
            select(MaintenanceRecord.maintenance_date)
            .where(
                MaintenanceRecord.asset_id == asset.id,
                MaintenanceRecord.status == "COMPLETED",
                MaintenanceRecord.maintenance_date.is_not(None),
            )
            .order_by(MaintenanceRecord.maintenance_date.desc())
            .limit(1)
        )

        # Handle missing or invalid lifecycle information.
        if (
            asset.installed_date is None
            or asset.expected_life_years is None
            or asset.expected_life_years <= 0
        ):
            return {
                "lifecycle_status": "UNAVAILABLE",
                "asset_age_years": None,
                "expected_end_of_life": None,
                "life_used_percentage": None,
                "maintenance_history_count": maintenance_history_count,
                "last_completed_maintenance_date": (
                    last_completed_date.isoformat()
                    if last_completed_date else None
                ),
            }

        installed_date = asset.installed_date
        expected_life = asset.expected_life_years

        # Calculate expected end-of-life date.
        end_year = installed_date.year + expected_life

        try:
            end_of_life = installed_date.replace(year=end_year)
        except ValueError:
            # Handle leap-day installation dates.
            end_of_life = installed_date.replace(
                year=end_year,
                day=28,
            )

        # Handle equipment with a future installation date.
        if installed_date > today:
            lifecycle_status = "NOT_YET_INSTALLED"
            asset_age_years = 0.0
            life_used_percentage = 0.0
        else:
            age_days = (today - installed_date).days

            asset_age_years = round(
                age_days / 365.2425, 2
            )

            life_used_percentage = round(
                (asset_age_years / expected_life) * 100,
                2,
            )

            if life_used_percentage > 100:
                lifecycle_status = "END_OF_LIFE"
            elif life_used_percentage >= 90:
                lifecycle_status = "NEAR_END_OF_LIFE"
            elif life_used_percentage >= 75:
                lifecycle_status = "AGING"
            else:
                lifecycle_status = "ACTIVE"

        return {
            "lifecycle_status": lifecycle_status,
            "asset_age_years": asset_age_years,
            "expected_end_of_life": end_of_life.isoformat(),
            "life_used_percentage": life_used_percentage,
            "maintenance_history_count": maintenance_history_count,
            "last_completed_maintenance_date": (
                last_completed_date.isoformat()
                if last_completed_date else None
            ),

        }
    def get_maintenance_schedule(
        self,
        asset: Asset,
        health_score: float,
        risk_level: str,
        telemetry_status: str,
        lifecycle_status: str,
    ):
        today = date.today()

        # Check whether an active work order already exists.
        existing_work_order = self.db.scalar(
            select(MaintenanceRecord)
            .where(
                MaintenanceRecord.asset_id == asset.id,
                MaintenanceRecord.status.in_(
                    ["SCHEDULED", "IN_PROGRESS"]
                ),
            )
            .order_by(MaintenanceRecord.maintenance_date.asc())
            .limit(1)
        )

        if existing_work_order:
            return {
                "schedule_status": "ALREADY_SCHEDULED",
                "recommended_date": (
                    existing_work_order.maintenance_date.isoformat()
                    if existing_work_order.maintenance_date
                    else None
                ),
                "priority": existing_work_order.priority,
                "reason": "An active maintenance work order already exists.",
                "existing_work_order_id": existing_work_order.id,
            }

        # Determine maintenance urgency.
        if telemetry_status == "STALE":
            days_until_maintenance = 2
            priority = "MEDIUM"
            action = "Inspect telemetry sensors and restore data connectivity."
            reason = "Equipment telemetry is outdated."

        else:
            risk_schedule = {
                "CRITICAL": (1, "CRITICAL"),
                "HIGH": (3, "HIGH"),
                "MEDIUM": (7, "MEDIUM"),
                "LOW": (30, "LOW"),
            }

            days_until_maintenance, priority = risk_schedule.get(
                risk_level,
                (30, "LOW"),
            )

            action = "Perform routine equipment inspection."
            reason = f"Equipment health score is {health_score}."

        # Adjust urgency based on asset lifecycle.
        lifecycle_schedule = {
            "END_OF_LIFE": 1,
            "NEAR_END_OF_LIFE": 3,
            "AGING": 7,
        }

        lifecycle_days = lifecycle_schedule.get(lifecycle_status)

        if lifecycle_days is not None:
            days_until_maintenance = min(
                days_until_maintenance,
                lifecycle_days,
            )

            if lifecycle_days <= 1:
                priority = "CRITICAL"
            elif lifecycle_days <= 3 and priority not in [
                "CRITICAL",
                "HIGH",
            ]:
                priority = "HIGH"

            reason += f" Lifecycle status: {lifecycle_status}."

        recommended_date = today + timedelta(
            days=days_until_maintenance
        )

        return {
            "schedule_status": "RECOMMENDED",
            "recommended_date": recommended_date.isoformat(),
            "days_until_maintenance": days_until_maintenance,
            "priority": priority,
            "recommended_action": action,
            "reason": reason,
            "existing_work_order_id": None,
        }
    def analyze_asset(self, asset_id: int):
        asset = self.db.get(Asset, asset_id)

        if not asset:
            return {"error": "Asset not found"}

        latest = self.db.scalar(
            select(AssetReading)
            .where(AssetReading.asset_id == asset_id)
            .order_by(AssetReading.recorded_at.desc())
            .limit(1)
        )

        if not latest:
            return {"error": "No telemetry available for this asset"}
                # Check whether the latest telemetry is recent.
        latest_timestamp = latest.recorded_at

        if latest_timestamp.tzinfo is None:
            latest_timestamp = latest_timestamp.replace(
                tzinfo=timezone.utc
            )

        current_time = datetime.now(timezone.utc)

        telemetry_age_hours = round(
            (current_time - latest_timestamp).total_seconds() / 3600,
            2,
        )

        telemetry_status = (
            "FRESH" if telemetry_age_hours <= 24 else "STALE"
        )

        # Use the most recent 7 days as the operating baseline.
        # Use the earliest 7 days as the healthy operating baseline.
        readings = self.db.scalars(
          select(AssetReading)
    .where(AssetReading.asset_id == asset_id)
    .order_by(AssetReading.recorded_at.asc())
    .limit(168)
).all()

        if len(readings) < 5:
            return {"error": "Insufficient historical readings for baseline"}

        def average(field):
            values = [
                getattr(reading, field)
                for reading in readings
                if getattr(reading, field) is not None
            ]
            return sum(values) / len(values) if values else 0.0

        baseline_temp = average("temperature_c")
        baseline_vibration = average("vibration_mm_s")
        baseline_current = average("current_a")

        if min(baseline_temp, baseline_vibration, baseline_current) <= 0:
            return {"error": "Invalid telemetry baseline"}

        result = calculate_health_score(
            temperature_c=latest.temperature_c or 0.0,
            vibration_mm_s=latest.vibration_mm_s or 0.0,
            current_a=latest.current_a or 0.0,
            baseline_temperature=baseline_temp,
            baseline_vibration=baseline_vibration,
            baseline_current=baseline_current,
        )
        lifecycle = self.get_asset_lifecycle(asset)
        maintenance_schedule = self.get_maintenance_schedule(
            asset=asset,
            health_score=result.health_score,
            risk_level=result.risk_level,
            telemetry_status=telemetry_status,
            lifecycle_status=lifecycle["lifecycle_status"],
        )
        return {
            "asset_id": asset.id,
            "asset_code": asset.asset_code,
            "asset_name": asset.asset_name,
            "asset_type": asset.asset_type,
            "health_score": result.health_score,
            "condition": result.condition,
            "risk_level": result.risk_level,
            "lifecycle": lifecycle,
            "maintenance_schedule": maintenance_schedule,
            "last_seen": latest.recorded_at.isoformat(),
            "telemetry_age_hours": telemetry_age_hours,
            "telemetry_status": telemetry_status,
            "latest_reading": {
                "recorded_at": latest.recorded_at.isoformat(),
                "temperature_c": latest.temperature_c,
                "vibration_mm_s": latest.vibration_mm_s,
                "current_a": latest.current_a,
            },
            "baseline": {
                "temperature_c": round(baseline_temp, 2),
                "vibration_mm_s": round(baseline_vibration, 2),
                "current_a": round(baseline_current, 2),
            },
            "recommendations": result.recommendations,
        }
    def analyze_facility(self, facility_id: int):
        assets = self.db.scalars(
            select(Asset)
            .where(Asset.facility_id == facility_id)
            .order_by(Asset.asset_code)
        ).all()

        results = [
            self.analyze_asset(asset.id)
            for asset in assets
        ]

        valid_results = [
            item for item in results
            if "health_score" in item
        ]

        alerts = []
        alert_generated_at = datetime.now(timezone.utc).isoformat()

        for asset in valid_results:

            # Stale telemetry: generate a data-quality warning.
            if asset["telemetry_status"] == "STALE":
                alerts.append({
                    "asset_id": asset["asset_id"],
                    "asset_code": asset["asset_code"],
                    "alert_type": "STALE_TELEMETRY",
                    "priority": "MEDIUM",
                    "generated_at": alert_generated_at,
                    "message": (
                        f"Asset telemetry is outdated by "
                        f"{asset['telemetry_age_hours']} hours."
                    ),
                    "recommendation": (
                        "Check sensor connectivity and verify "
                        "the latest equipment readings."
                    ),
                })
                continue

            # Generate equipment health alerts only for fresh telemetry.
            score = asset["health_score"]

            if score < 30:
                priority = "CRITICAL"
            elif score < 50:
                priority = "HIGH"
            elif score < 70:
                priority = "MEDIUM"
            elif score < 85:
                priority = "LOW"
            else:
                continue

            alerts.append({
                "asset_id": asset["asset_id"],
                "asset_code": asset["asset_code"],
                "alert_type": "EQUIPMENT_HEALTH",
                "priority": priority,
                "generated_at": alert_generated_at,
                "health_score": score,
                "condition": asset["condition"],
                "message": (
                    f"{asset['asset_name']} requires maintenance "
                    f"attention. Health score: {score}."
                ),
                "recommendations": asset["recommendations"],
            })

        return {
            "facility_id": facility_id,
            "total_assets": len(assets),
            "analyzed_assets": len(valid_results),
            "total_alerts": len(alerts),
            "assets": results,
            "alerts": alerts,
        }


import argparse
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, func, select

from app.database.session import SessionLocal
from app.models import (
    Asset,
    AssetReading,
    EnergyReading,
    Facility,
    MaintenanceRecord,
)


ASSET_PLAN = [
    ("CH-01", "Chiller 1", "CHILLER", 7.0, 4.5, 95.0),
    ("CH-02", "Chiller 2", "CHILLER", 7.5, 4.8, 98.0),
    ("AHU-01", "AHU 1", "AHU", 5.0, 2.5, 18.0),
    ("AHU-02", "AHU 2", "AHU", 5.2, 2.7, 19.0),
    ("AHU-03", "AHU 3", "AHU", 5.5, 2.8, 20.0),
    ("AHU-04", "AHU 4", "AHU", 5.1, 2.6, 18.5),
    ("PUMP-01", "Water Pump 1", "PUMP", 4.0, 3.0, 15.0),
    ("PUMP-02", "Water Pump 2", "PUMP", 4.2, 3.2, 16.0),
    ("CT-01", "Cooling Tower", "COOLING_TOWER", 6.0, 3.5, 25.0),
    ("EF-01", "Exhaust Fan", "EXHAUST_FAN", 4.5, 2.0, 8.0),
]

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "maintenance_ground_truth.csv"
)


def generate_reading(asset, timestamp, hours_running, degradation, rng):
    """Generate realistic synthetic equipment telemetry."""

    temperature = asset["base_temp"] + rng.uniform(-0.8, 0.8)
    vibration = asset["base_vibration"] + rng.uniform(-0.25, 0.25)
    current = asset["base_current"] + rng.uniform(-1.5, 1.5)

    temperature += degradation * rng.uniform(2.0, 4.0)
    vibration += degradation * rng.uniform(1.0, 2.5)
    current += degradation * rng.uniform(2.0, 5.0)

    # Occasional harmless sensor spikes.
    if rng.random() < 0.003:
        vibration += rng.uniform(1.0, 2.0)

    if rng.random() < 0.002:
        temperature += rng.uniform(2.0, 4.0)

    return {
        "recorded_at": timestamp,
        "temperature_c": round(max(0, temperature), 2),
        "vibration_mm_s": round(max(0, vibration), 2),
        "current_a": round(max(0, current), 2),
        "runtime_hours": round(hours_running, 2),
    }


def generate_facility_data(db, facility, days, rng, dry_run):
    existing = db.scalar(
        select(func.count(Asset.id)).where(
            Asset.facility_id == facility.id
        )
    )

    if existing:
        print(
            f"[SKIP] {facility.name}: already has {existing} assets. "
            "Existing data preserved."
        )
        return []

    latest_energy = db.scalar(
        select(func.max(EnergyReading.recorded_at)).where(
            EnergyReading.facility_id == facility.id
        )
    )

    end_time = latest_energy or datetime.now(timezone.utc)

    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    start_time = end_time - timedelta(days=days)

    # Three historical failures, two currently degrading assets.
    states = ["FAILED"] * 3 + ["DEGRADING"] * 2 + ["HEALTHY"] * 5
    rng.shuffle(states)

    truth_rows = []
    total_readings = 0

    for asset_spec, state in zip(ASSET_PLAN, states):
        code, name, asset_type, temp, vibration, current = asset_spec

        asset = {
            "base_temp": temp,
            "base_vibration": vibration,
            "base_current": current,
        }

        if state == "FAILED":
            failure_time = end_time - timedelta(
                days=rng.randint(12, 28)
            )
            degradation_start = failure_time - timedelta(days=35)
        elif state == "DEGRADING":
            failure_time = end_time + timedelta(
                days=rng.randint(7, 21)
            )
            degradation_start = end_time - timedelta(days=35)
        else:
            failure_time = None
            degradation_start = None

        if state != "HEALTHY":
            truth_rows.append({
                "facility_id": facility.id,
                "facility_name": facility.name,
                "asset_code": code,
                "asset_type": asset_type,
                "state": state,
                "degradation_start": degradation_start.isoformat(),
                "failure_time": (
                    failure_time.isoformat() if failure_time else ""
                ),
            })

        asset_record = Asset(
            facility_id=facility.id,
            asset_code=code,
            asset_name=name,
            asset_type=asset_type,
            status="ACTIVE",
            installed_date=(end_time - timedelta(days=365 * 3)).date(),
            expected_life_years=10,
        )

        db.add(asset_record)
        db.flush()

        readings = []
        runtime_hours = rng.uniform(3000, 12000)

        for hour in range(days * 24):
            timestamp = start_time + timedelta(hours=hour)

            if state == "FAILED" and timestamp > failure_time:
                continue

            if state == "HEALTHY":
                degradation = 0.0
            elif timestamp < degradation_start:
                degradation = 0.0
            else:
                total_period = max(
                    1,
                    (end_time - degradation_start).total_seconds()
                    / 3600,
                )
                elapsed = (
                    timestamp - degradation_start
                ).total_seconds() / 3600

                degradation = min(1.0, max(0.0, elapsed / total_period))

            reading = generate_reading(
                asset,
                timestamp,
                runtime_hours,
                degradation,
                rng,
            )

            readings.append(
                AssetReading(
                    asset_id=asset_record.id,
                    **reading,
                )
            )

            runtime_hours += rng.uniform(0.5, 1.0)

            if len(readings) >= 500:
                db.add_all(readings)
                total_readings += len(readings)
                readings = []

        if readings:
            db.add_all(readings)
            total_readings += len(readings)

        if state == "FAILED":
            db.add(
                MaintenanceRecord(
                    asset_id=asset_record.id,
                    issue_type="EQUIPMENT_FAILURE",
                    description=(
                        "Synthetic historical equipment failure "
                        "generated for predictive maintenance testing."
                    ),
                    maintenance_date=failure_time.date(),
                    status="COMPLETED",
                    priority="HIGH",
                    cost_inr=round(rng.uniform(15000, 50000), 2),
                    source="HISTORICAL",
                )
            )

    if not dry_run:
        db.commit()

    print(
        f"[{'DRY RUN' if dry_run else 'CREATED'}] {facility.name}: "
        f"10 assets, approximately {total_readings} readings"
    )

    return truth_rows


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic predictive maintenance data."
    )
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.days < 1 or args.days > 365:
        raise ValueError("Days must be between 1 and 365.")

    rng = random.Random(42)
    all_truth = []

    with SessionLocal() as db:
        facilities = db.scalars(
            select(Facility).order_by(Facility.id)
        ).all()

        if not facilities:
            print("No facilities found. Nothing to generate.")
            return

        for facility in facilities:
            try:
                truth = generate_facility_data(
                    db,
                    facility,
                    args.days,
                    rng,
                    args.dry_run,
                )
                all_truth.extend(truth)
            except Exception:
                db.rollback()
                raise

    if not args.dry_run and all_truth:
        GROUND_TRUTH_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with GROUND_TRUTH_PATH.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=all_truth[0].keys(),
            )
            writer.writeheader()
            writer.writerows(all_truth)

        print(f"Ground truth saved: {GROUND_TRUTH_PATH}")

    print("Generation process finished.")


if __name__ == "__main__":
    main()

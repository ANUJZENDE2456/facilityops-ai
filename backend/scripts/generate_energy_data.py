#!/usr/bin/env python3
"""
Synthetic Energy Data Generator for Agentic FacilityOps AI Platform.

Simulates realistic 90-day hourly historical telemetry across submeters
(HVAC, Lighting, Plug Load) and Main Meter with diurnal curves, occupancy
patterns, and injected realistic operational anomalies.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

# -----------------------------------------------------------------------------
# Path and Environment Setup
# -----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import SessionLocal  # noqa: E402
from app.models import EnergyReading, Facility  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("energy_generator")

# -----------------------------------------------------------------------------
# Configuration & Constants
# -----------------------------------------------------------------------------
METER_HVAC = "HVAC-01"
METER_LIGHTING = "LIGHTING-01"
METER_PLUG = "PLUG-LOAD-01"
METER_MAIN = "MAIN-METER-01"

METERS = [METER_HVAC, METER_LIGHTING, METER_PLUG, METER_MAIN]


# -----------------------------------------------------------------------------
# Anomaly Event Definitions
# -----------------------------------------------------------------------------
class AnomalyEvent:
    """Defines an injected operational anomaly window."""

    def __init__(
        self,
        name: str,
        meter_id: str,
        start_hour: int,
        duration_hours: int,
        label: str,
        severity: str,
        description: str,
        power_adder: Optional[float] = None,
        power_override: Optional[float] = None,
    ):
        self.name = name
        self.meter_id = meter_id
        self.start_hour = start_hour
        self.duration_hours = duration_hours
        self.end_hour = start_hour + duration_hours
        self.label = label
        self.severity = severity
        self.description = description
        self.power_adder = power_adder
        self.power_override = power_override

    def applies_to(self, hour_index: int, meter_id: str) -> bool:
        return (
            self.meter_id == meter_id
            and self.start_hour <= hour_index < self.end_hour
        )

    def apply(self, hour_index: int, base_kw: float) -> float:
        if self.power_override is not None:
            return self.power_override
        if self.power_adder is not None:
            return base_kw + self.power_adder
        return base_kw


def build_anomalies(total_hours: int) -> List[AnomalyEvent]:
    """
    Constructs realistic anomaly scenarios mapped to specific timeline offsets.
    Total hours = 2160 (90 days * 24 hours).
    Chronological partition:
      - Training: Hours 0 to 1,511 (Days 0 to 62, first 70%)
      - Testing:  Hours 1,512 to 2,159 (Days 63 to 89, final 30%)
    Ensures all four meters have multiple anomaly scenarios in both partitions.
    """
    return [
        # =====================================================================
        # PART 1: TRAINING PERIOD ANOMALIES (Hours 0 to 1,511)
        # =====================================================================
        # 1. HVAC-01: Unexpected Night Consumption - Day 12 (22:00 to 06:00, 8h)
        AnomalyEvent(
            name="HVAC Training Night Override Failure",
            meter_id=METER_HVAC,
            start_hour=286,
            duration_hours=8,
            label="unexpected_night_consumption",
            severity="HIGH",
            description="HVAC chiller schedule override failed; chiller ran continuously at full cooling overnight",
            power_adder=80.0,
        ),
        # 2. LIGHTING-01: Unexpected Night Consumption - Day 18 (22:00 to 06:00, 8h)
        AnomalyEvent(
            name="Lighting Training Overnight Illumination",
            meter_id=METER_LIGHTING,
            start_hour=430,
            duration_hours=8,
            label="unexpected_night_consumption",
            severity="MEDIUM",
            description="Full-floor high-bay lighting remained energized overnight following office deep-cleaning",
            power_override=38.0,
        ),
        # 3. HVAC-01: Sudden Power Spike - Day 25 at 14:00 (1h)
        AnomalyEvent(
            name="Chiller Compressor Inrush Surge",
            meter_id=METER_HVAC,
            start_hour=614,
            duration_hours=1,
            label="power_spike",
            severity="CRITICAL",
            description="Chiller compressor startup electrical transient and severe power surge",
            power_adder=145.0,
        ),
        # 4. PLUG-LOAD-01: Sustained High Consumption - Day 29 to 30 (24h continuous)
        AnomalyEvent(
            name="Unapproved Continuous Batch Compute Job",
            meter_id=METER_PLUG,
            start_hour=696,
            duration_hours=24,
            label="sustained_high_consumption",
            severity="HIGH",
            description="Unapproved heavy batch computing workload running continuously across workstation farm",
            power_adder=35.0,
        ),
        # 5. LIGHTING-01: Sudden Power Spike - Day 36 at 10:00 (1h)
        AnomalyEvent(
            name="Lighting Busway Electrical Surge",
            meter_id=METER_LIGHTING,
            start_hour=874,
            duration_hours=1,
            label="power_spike",
            severity="MEDIUM",
            description="High-voltage lighting panel transient spike and power surge",
            power_adder=35.0,
        ),
        # 6. HVAC-01: Sustained High Consumption - Day 44 to 45 (36h continuous)
        AnomalyEvent(
            name="Stuck Economizer Damper Malfunction",
            meter_id=METER_HVAC,
            start_hour=1056,
            duration_hours=36,
            label="sustained_high_consumption",
            severity="CRITICAL",
            description="Stuck economizer damper and simultaneous reheat cycle malfunction causing 36h cooling fight",
            power_override=175.0,
        ),
        # 7. PLUG-LOAD-01: Sudden Power Spike - Day 52 at 10:00 (1h)
        AnomalyEvent(
            name="Server Room UPS Battery Test Surge",
            meter_id=METER_PLUG,
            start_hour=1258,
            duration_hours=1,
            label="power_spike",
            severity="HIGH",
            description="Server lab equipment electrical fault and temporary high load surge",
            power_adder=80.0,
        ),

        # =====================================================================
        # PART 2: TESTING PERIOD ANOMALIES (Hours 1,512 to 2,159)
        # =====================================================================
        # 8. HVAC-01: Unexpected Night Consumption - Day 66 (22:00 to 06:00, 8h)
        AnomalyEvent(
            name="HVAC Test Night Override Active",
            meter_id=METER_HVAC,
            start_hour=1582,
            duration_hours=8,
            label="unexpected_night_consumption",
            severity="HIGH",
            description="After-hours chiller cooling override left active overnight",
            power_adder=85.0,
        ),
        # 9. LIGHTING-01: Unexpected Night Consumption - Day 70 (22:00 to 06:00, 8h)
        AnomalyEvent(
            name="Lighting Test Control Relay Stuck",
            meter_id=METER_LIGHTING,
            start_hour=1678,
            duration_hours=8,
            label="unexpected_night_consumption",
            severity="MEDIUM",
            description="Architectural lighting control relay stuck closed, keeping lights energized overnight",
            power_override=36.0,
        ),
        # 10. HVAC-01: Sudden Power Spike - Day 74 at 14:00 (1h)
        AnomalyEvent(
            name="HVAC Chiller Pump Motor Transient Surge",
            meter_id=METER_HVAC,
            start_hour=1790,
            duration_hours=1,
            label="power_spike",
            severity="CRITICAL",
            description="Chiller pump motor transient surge during peak afternoon thermal load",
            power_adder=140.0,
        ),
        # 11. PLUG-LOAD-01: Sudden Power Spike - Day 76 at 10:00 (1h)
        AnomalyEvent(
            name="Server Rack Power Supply Fault Surge",
            meter_id=METER_PLUG,
            start_hour=1834,
            duration_hours=1,
            label="power_spike",
            severity="HIGH",
            description="Server rack power distribution unit fault and localized power spike",
            power_adder=85.0,
        ),
        # 12. LIGHTING-01: Sudden Power Spike - Day 80 at 10:00 (1h)
        AnomalyEvent(
            name="Lighting High-Voltage Circuit Transient",
            meter_id=METER_LIGHTING,
            start_hour=1930,
            duration_hours=1,
            label="power_spike",
            severity="MEDIUM",
            description="Lighting circuit transient voltage surge and ballast spike",
            power_adder=30.0,
        ),
        # 13. HVAC-01: Sustained High Consumption - Day 83 to 84 (28h continuous)
        AnomalyEvent(
            name="Cooling Valve Actuator Failure",
            meter_id=METER_HVAC,
            start_hour=1992,
            duration_hours=28,
            label="sustained_high_consumption",
            severity="CRITICAL",
            description="Cooling valve actuator seized fully open, forcing chilled water pump at continuous 100% capacity",
            power_override=170.0,
        ),
        # 14. PLUG-LOAD-01: Weekend Unauthorized Consumption - Day 86 Sunday (08:00 to 20:00, 12h)
        AnomalyEvent(
            name="Unauthorized Weekend Workstation Compute Load",
            meter_id=METER_PLUG,
            start_hour=2072,
            duration_hours=12,
            label="weekend_unauthorized_consumption",
            severity="HIGH",
            description="Unapproved weekend high-intensity compute batch job executed across office workstations",
            power_adder=45.0,
        ),
        # 15. PLUG-LOAD-01: Sustained High Consumption - Day 88 (06:00 to 24:00, 18h)
        AnomalyEvent(
            name="Unmonitored Test Cluster Sustained Workload",
            meter_id=METER_PLUG,
            start_hour=2112,
            duration_hours=18,
            label="sustained_high_consumption",
            severity="HIGH",
            description="Continuous compute load on test servers left running unthrottled through business and night hours",
            power_adder=35.0,
        ),
    ]


# -----------------------------------------------------------------------------
# Base Electrical Load Simulation
# -----------------------------------------------------------------------------
def simulate_submeter_power(
    dt: datetime,
    hour_idx: int,
    total_hours: int,
) -> Tuple[float, float, float]:
    """
    Simulates base active power (kW) for HVAC, Lighting, and Plug Load for a given hour.
    Incorporates weekday/weekend patterns, diurnal curves, and ambient thermal cycle.
    """
    weekday = dt.weekday()  # 0=Mon, ..., 6=Sun
    is_weekend = weekday >= 5
    hour = dt.hour
    day_idx = hour_idx // 24

    # Outdoor thermal temperature proxy (seasonal curve + diurnal variation)
    temp_seasonal = 22.0 + 7.0 * math.sin(2.0 * math.pi * day_idx / 180.0)
    temp_diurnal = 6.5 * math.sin(2.0 * math.pi * (hour - 9) / 24.0)
    ambient_temp = temp_seasonal + temp_diurnal + np.random.normal(0, 1.2)

    # 1. HVAC-01 Load Calculation
    if is_weekend:
        # Weekend setback
        hvac_kw = 22.0 + max(0.0, (ambient_temp - 24.0) * 2.5) + np.random.normal(0, 1.5)
    else:
        if 8 <= hour <= 18:
            # Working hours: full occupancy and thermal load
            occupancy_boost = 18.0 * math.sin(math.pi * (hour - 8) / 10.0)
            cooling_demand = max(0.0, (ambient_temp - 21.0) * 4.5)
            hvac_kw = 72.0 + occupancy_boost + cooling_demand + np.random.normal(0, 2.5)
        elif (6 <= hour < 8) or (18 < hour <= 21):
            # Ramp-up / Ramp-down
            hvac_kw = 42.0 + np.random.normal(0, 2.0)
        else:
            # Night setback
            hvac_kw = 20.0 + np.random.normal(0, 1.5)

    hvac_kw = max(12.0, hvac_kw)

    # 2. LIGHTING-01 Load Calculation
    if is_weekend:
        if 8 <= hour <= 18:
            lighting_kw = 8.0 + np.random.normal(0, 0.8)
        else:
            lighting_kw = 4.0 + np.random.normal(0, 0.3)
    else:
        if 8 <= hour <= 18:
            lighting_kw = 36.0 + np.random.normal(0, 1.2)
        elif (6 <= hour < 8) or (18 < hour <= 21):
            lighting_kw = 18.0 + np.random.normal(0, 1.0)
        else:
            lighting_kw = 4.2 + np.random.normal(0, 0.4)

    lighting_kw = max(2.5, lighting_kw)

    # 3. PLUG-LOAD-01 Load Calculation
    if is_weekend:
        plug_kw = 16.0 + np.random.normal(0, 1.0)
    else:
        if 8 <= hour <= 18:
            occupancy_plug = 10.0 * math.sin(math.pi * (hour - 8) / 10.0)
            plug_kw = 42.0 + occupancy_plug + np.random.normal(0, 1.8)
        elif (6 <= hour < 8) or (18 < hour <= 21):
            plug_kw = 25.0 + np.random.normal(0, 1.2)
        else:
            plug_kw = 13.5 + np.random.normal(0, 0.8)

    plug_kw = max(10.0, plug_kw)

    return (
        round(float(hvac_kw), 3),
        round(float(lighting_kw), 3),
        round(float(plug_kw), 3),
    )


def compute_voltage_and_current(power_kw: float) -> Tuple[float, float]:
    """
    Computes realistic 3-phase line voltage and current for given active power.
    Nominal 415V with slight load-dependent sag and ~0.92 power factor.
    """
    voltage_v = float(
        np.clip(np.random.normal(415.0, 1.5) - (power_kw / 600.0), 405.0, 425.0)
    )
    # 3-phase current: I = (P * 1000) / (sqrt(3) * V * PF)
    pf = 0.92
    current_a = (power_kw * 1000.0) / (math.sqrt(3) * voltage_v * pf)
    return round(voltage_v, 2), round(float(current_a), 2)


# -----------------------------------------------------------------------------
# Main Generation Logic
# -----------------------------------------------------------------------------
def generate_dataset(
    days: int = 90,
    seed: int = 42,
) -> Tuple[List[datetime], Dict[str, List[dict]], List[dict]]:
    """
    Generates 90 days of hourly energy telemetry with injected anomalies.
    Returns:
      - timestamps: List of hourly timestamps
      - meter_records: Dict mapping meter_id -> list of reading dicts
      - ground_truth_anomalies: List of anomaly label records
    """
    # Fix random seeds for reproducible output
    np.random.seed(seed)
    random.seed(seed)

    # Hourly timestamps ending at the latest completed hour
    now = datetime.now(timezone.utc)
    latest_completed_hour = now.replace(minute=0, second=0, microsecond=0)
    total_hours = days * 24
    start_time = latest_completed_hour - timedelta(hours=total_hours)

    timestamps = [
        start_time + timedelta(hours=i) for i in range(1, total_hours + 1)
    ]

    anomalies = build_anomalies(total_hours)
    ground_truth_records: List[dict] = []

    meter_data: Dict[str, List[dict]] = {m: [] for m in METERS}

    for idx, dt in enumerate(timestamps):
        hvac_base, lighting_base, plug_base = simulate_submeter_power(
            dt, idx, total_hours
        )

        hvac_kw = hvac_base
        lighting_kw = lighting_base
        plug_kw = plug_base

        hour_anomalies: List[Tuple[str, AnomalyEvent]] = []

        # Check and apply anomalies to submeters
        for anomaly in anomalies:
            if anomaly.applies_to(idx, METER_HVAC):
                hvac_kw = anomaly.apply(idx, hvac_kw)
                hour_anomalies.append((METER_HVAC, anomaly))
            elif anomaly.applies_to(idx, METER_LIGHTING):
                lighting_kw = anomaly.apply(idx, lighting_kw)
                hour_anomalies.append((METER_LIGHTING, anomaly))
            elif anomaly.applies_to(idx, METER_PLUG):
                plug_kw = anomaly.apply(idx, plug_kw)
                hour_anomalies.append((METER_PLUG, anomaly))

        # Main meter is the combined consumption of all submeters
        main_kw = round(hvac_kw + lighting_kw + plug_kw, 3)

        # Record submeter and main meter anomaly labels in ground truth
        iso_timestamp = dt.isoformat()
        for meter_id, anom in hour_anomalies:
            ground_truth_records.append(
                {
                    "meter_id": meter_id,
                    "timestamp": iso_timestamp,
                    "anomaly_label": anom.label,
                    "severity": anom.severity,
                    "description": anom.description,
                }
            )
            # Main meter directly reflects the submeter anomaly
            ground_truth_records.append(
                {
                    "meter_id": METER_MAIN,
                    "timestamp": iso_timestamp,
                    "anomaly_label": anom.label,
                    "severity": anom.severity,
                    "description": f"Combined meter reflects submeter anomaly: {anom.description}",
                }
            )

        # Assemble reading objects
        submeter_values = [
            (METER_HVAC, hvac_kw),
            (METER_LIGHTING, lighting_kw),
            (METER_PLUG, plug_kw),
            (METER_MAIN, main_kw),
        ]

        for m_id, kw in submeter_values:
            kw = round(float(kw), 3)
            # Energy consumed during that 1-hour interval (kWh = kW * 1h)
            kwh = round(kw * 1.0, 3)
            voltage_v, current_a = compute_voltage_and_current(kw)

            meter_data[m_id].append(
                {
                    "meter_id": m_id,
                    "power_kw": kw,
                    "energy_kwh": kwh,
                    "voltage_v": voltage_v,
                    "current_a": current_a,
                    "recorded_at": dt,
                }
            )

    return timestamps, meter_data, ground_truth_records


def save_ground_truth_csv(
    ground_truth_records: List[dict],
    csv_path: str,
) -> None:
    """Saves anomaly ground-truth records to CSV."""
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    fieldnames = ["meter_id", "timestamp", "anomaly_label", "severity", "description"]
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ground_truth_records)
    logger.info(f"Anomaly ground-truth exported ({len(ground_truth_records)} rows) -> {csv_path}")


def get_or_create_demo_facility(
    db,
    facility_name: str = "Demo Corporate Office",
) -> Facility:
    """Finds or creates the demo facility record."""
    facility = db.query(Facility).filter(Facility.name == facility_name).first()
    if not facility:
        facility = Facility(
            name=facility_name,
            location="100 Innovation Way, Suite 400, San Jose, CA",
            building_type="Commercial Office",
        )
        db.add(facility)
        db.commit()
        db.refresh(facility)
        logger.info(f"Created demo facility: '{facility.name}' (ID: {facility.id})")
    else:
        logger.info(f"Found existing demo facility: '{facility.name}' (ID: {facility.id})")
    return facility


def persist_readings(
    facility_id: int,
    meter_data: Dict[str, List[dict]],
    overwrite: bool = True,
) -> int:
    """
    Atomically persists generated energy readings into the database.
    Deletes prior readings only for the specified facility and commits all
    readings in a single atomic transaction. Rolls back entirely on failure.
    """
    db = SessionLocal()
    try:
        existing_count = (
            db.query(EnergyReading)
            .filter(EnergyReading.facility_id == facility_id)
            .count()
        )

        if existing_count > 0:
            if not overwrite:
                logger.warning(
                    f"Facility ID {facility_id} already has {existing_count} readings. "
                    "Skipping insertion (--no-overwrite specified)."
                )
                return 0

            logger.info(
                f"Staging deletion of {existing_count} existing readings for facility ID {facility_id}..."
            )
            db.query(EnergyReading).filter(
                EnergyReading.facility_id == facility_id
            ).delete(synchronize_session=False)

        # Flatten records across all meters sorted chronologically
        all_readings: List[EnergyReading] = []
        for meter_id in METERS:
            for item in meter_data[meter_id]:
                all_readings.append(
                    EnergyReading(
                        facility_id=facility_id,
                        meter_id=item["meter_id"],
                        power_kw=item["power_kw"],
                        energy_kwh=item["energy_kwh"],
                        voltage_v=item["voltage_v"],
                        current_a=item["current_a"],
                        recorded_at=item["recorded_at"],
                    )
                )

        logger.info(f"Staging {len(all_readings)} readings into database session...")
        batch_size = 2000
        for i in range(0, len(all_readings), batch_size):
            batch = all_readings[i : i + batch_size]
            db.add_all(batch)
            db.flush()

        # Commit once after all batches are staged atomically
        db.commit()
        logger.info(f"Successfully committed {len(all_readings)} records to database.")
        return len(all_readings)

    except Exception as exc:
        db.rollback()
        logger.error(f"Database error during persistence; transaction rolled back: {exc}")
        raise
    finally:
        db.close()


def print_summary(
    facility_id: Optional[int],
    facility_name: str,
    timestamps: List[datetime],
    total_readings: int,
    anomaly_records: List[dict],
    csv_path: str,
    dry_run: bool = False,
) -> None:
    """Prints a structured summary of the generated dataset."""
    unique_anomaly_hours = len(
        {r["timestamp"] for r in anomaly_records}
    )
    anomaly_counts_by_type: Dict[str, int] = {}
    for r in anomaly_records:
        label = r["anomaly_label"]
        anomaly_counts_by_type[label] = anomaly_counts_by_type.get(label, 0) + 1

    print("\n" + "=" * 80)
    print("Agentic FacilityOps AI Platform - Energy Data Generation Summary")
    print("=" * 80)
    if dry_run:
        print("EXECUTION MODE:         DRY RUN")
        print("DATABASE STATUS:        UNTOUCHED (No records queried, deleted, or inserted)")
        print(f"GROUND-TRUTH CSV:       WRITTEN ({len(anomaly_records)} anomaly rows exported)")
    else:
        print("EXECUTION MODE:         LIVE DATABASE INSERTION")
    print(f"Facility Name:          {facility_name}")
    print(f"Facility ID:            {facility_id if facility_id is not None else 'N/A (Dry Run - skipped)'}")
    print(f"Building Type:          Commercial Office")
    print(f"Meters Configured (4):  {', '.join(METERS)}")
    print("-" * 80)
    print(f"Date Range Start:       {timestamps[0].isoformat()}")
    print(f"Date Range End:         {timestamps[-1].isoformat()}")
    print(f"Total Time Horizon:     {len(timestamps)} hours ({(len(timestamps) / 24):.0f} days)")
    print(f"Total Readings Created: {total_readings:,}")
    print("-" * 80)
    print(f"Total Anomaly Rows:     {len(anomaly_records)}")
    print(f"Anomalous Time Windows: {unique_anomaly_hours} hours")
    print("Injected Anomaly Breakdown:")
    for label, count in sorted(anomaly_counts_by_type.items()):
        print(f"  - {label:<35}: {count:>3} rows")
    print(f"Ground-Truth CSV Path:  {os.path.abspath(csv_path)}")
    print("=" * 80 + "\n")


# -----------------------------------------------------------------------------
# CLI Entrypoint
# -----------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic 90-day hourly energy telemetry with operational anomalies."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of historical days to simulate (default: 90)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Fixed random seed for reproducible generation (default: 42)",
    )
    parser.add_argument(
        "--facility-name",
        type=str,
        default="Demo Corporate Office",
        help="Name of the demo facility (default: 'Demo Corporate Office')",
    )
    parser.add_argument(
        "--csv-path",
        type=str,
        default=os.path.join(BACKEND_DIR, "data", "anomaly_ground_truth.csv"),
        help="Path where the anomaly ground-truth CSV will be saved",
    )
    parser.add_argument(
        "--no-overwrite",
        dest="overwrite",
        action="store_false",
        default=True,
        help="Do not overwrite existing readings if they already exist for the facility (skip insertion)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run generation and create ground-truth CSV without connecting to the database",
    )

    args = parser.parse_args()

    logger.info("Starting synthetic energy data generation...")
    logger.info(f"Horizon: {args.days} days | Seed: {args.seed} | Facility: '{args.facility_name}'")

    # 1. Generate full dataset and anomalies
    timestamps, meter_data, anomaly_records = generate_dataset(
        days=args.days,
        seed=args.seed,
    )

    total_readings = sum(len(readings) for readings in meter_data.values())

    # 2. Export ground-truth anomaly CSV
    save_ground_truth_csv(anomaly_records, args.csv_path)

    # 3. Persist to database if not in dry-run mode
    facility_id: Optional[int] = None
    if not args.dry_run:
        db = SessionLocal()
        try:
            facility = get_or_create_demo_facility(db, facility_name=args.facility_name)
            facility_id = facility.id
        finally:
            db.close()

        persist_readings(
            facility_id=facility_id,
            meter_data=meter_data,
            overwrite=args.overwrite,
        )
    else:
        logger.info(
            "Dry-run enabled: database operations skipped (no database changes made). "
            f"Ground-truth CSV generated and written to {args.csv_path}."
        )

    # 4. Print detailed summary
    print_summary(
        facility_id=facility_id,
        facility_name=args.facility_name,
        timestamps=timestamps,
        total_readings=total_readings,
        anomaly_records=anomaly_records,
        csv_path=args.csv_path,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

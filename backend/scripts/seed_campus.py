"""
Create 2 extra demo buildings from the existing facility's data (3-building campus).
Run from the backend folder:   python -m scripts.seed_campus
Safe to re-run: buildings that already exist are skipped.
"""
import random
from sqlalchemy import select

from app.database import SessionLocal
from app.models.energy_reading import EnergyReading
from app.models.facility import Facility

# name, location, type, size factor, seed, anomaly events: (hours_before_latest, duration_h, meter, extra_kw)
BUILDINGS = [
    ("Tech Campus - Tower B", "Pune, Maharashtra", "Commercial", 1.05, 101,
     [(40, 3, "HVAC-01", 45.0), (95, 2, "PLUG-LOAD-01", 28.0)]),
    ("Research Annex C", "Pune, Maharashtra", "Laboratory", 0.95, 202,
     [(26, 4, "HVAC-01", 40.0), (70, 3, "LIGHTING-01", 14.0)]),
]


def main():
    db = SessionLocal()
    try:
        source = db.scalars(select(Facility).order_by(Facility.id)).first()
        if source is None:
            raise SystemExit("No source facility found. Generate/load the base data first.")
        base = db.scalars(
            select(EnergyReading).where(EnergyReading.facility_id == source.id)
        ).all()
        latest = max(r.recorded_at for r in base)
        print(f"Source: {source.name} ({len(base)} readings)")

        for name, loc, btype, scale, seed, events in BUILDINGS:
            if db.scalar(select(Facility).where(Facility.name == name)):
                print(f"Skip (exists): {name}")
                continue
            rng = random.Random(seed)
            fac = Facility(name=name, location=loc, building_type=btype)
            db.add(fac)
            db.flush()

            rows = []
            for r in base:
                m = scale * (1 + rng.gauss(0, 0.03))
                power, energy = r.power_kw * m, r.energy_kwh * m
                for hours_before, dur, meter, extra in events:
                    age = (latest - r.recorded_at).total_seconds() / 3600
                    if hours_before - dur < age <= hours_before and r.meter_id in (meter, "MAIN-METER-01"):
                        power += extra
                        energy += extra
                rows.append(EnergyReading(
                    facility_id=fac.id, meter_id=r.meter_id,
                    power_kw=round(power, 3), energy_kwh=round(energy, 3),
                    voltage_v=r.voltage_v, current_a=r.current_a, recorded_at=r.recorded_at,
                ))
            db.bulk_save_objects(rows)
            db.commit()
            print(f"Created: {name} (id={fac.id}) with {len(rows)} readings and {len(events)} injected anomaly events")
    finally:
        db.close()


if __name__ == "__main__":
    main()

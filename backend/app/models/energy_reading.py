"""
SQLAlchemy ORM model for EnergyReading time-series telemetry entities.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.facility import Facility


class EnergyReading(Base):
    """
    Represents an energy telemetry reading from a smart meter or submeter.
    """

    __tablename__ = "energy_readings"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        doc="Unique identifier for the telemetry reading record",
    )
    facility_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("facilities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key reference to the associated facility",
    )
    meter_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Identifier of the physical or virtual meter recording telemetry",
    )
    power_kw: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Active power demand measured in kilowatts (kW)",
    )
    energy_kwh: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Cumulative energy consumption measured in kilowatt-hours (kWh)",
    )
    voltage_v: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Voltage measurement in volts (V)",
    )
    current_a: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Electric current measurement in amperes (A)",
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Timestamp when the reading was recorded (UTC timezone-aware)",
    )

    # Composite indexes for high-frequency time-series queries
    __table_args__ = (
        Index("ix_energy_readings_facility_recorded_at", "facility_id", "recorded_at"),
        Index("ix_energy_readings_meter_recorded_at", "meter_id", "recorded_at"),
    )

    # Relationships
    facility: Mapped[Facility] = relationship(
        "Facility",
        back_populates="energy_readings",
        doc="Associated facility entity",
    )

    def __repr__(self) -> str:
        return (
            f"<EnergyReading(id={self.id}, facility_id={self.facility_id}, "
            f"meter_id='{self.meter_id}', power_kw={self.power_kw}, "
            f"energy_kwh={self.energy_kwh}, recorded_at='{self.recorded_at}')>"
        )

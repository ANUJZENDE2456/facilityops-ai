"""
SQLAlchemy ORM model for Facility entities.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.energy_reading import EnergyReading


class Facility(Base):
    """
    Represents a physical facility, building, or operational campus.
    """

    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        doc="Unique identifier for the facility",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Name of the facility or building",
    )
    location: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Geographic location or address of the facility",
    )
    building_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        doc="Type/classification of the building (e.g., Commercial, Industrial, Data Center)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the facility record was created (UTC timezone-aware)",
    )

    # Relationships
    energy_readings: Mapped[List[EnergyReading]] = relationship(
        "EnergyReading",
        back_populates="facility",
        cascade="all, delete-orphan",
        passive_deletes=True,
        doc="Collection of energy telemetry readings associated with this facility",
    )

    def __repr__(self) -> str:
        return (
            f"<Facility(id={self.id}, name='{self.name}', "
            f"building_type='{self.building_type}', location='{self.location}')>"
        )

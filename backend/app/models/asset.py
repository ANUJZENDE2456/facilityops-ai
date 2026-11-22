
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Asset(Base):
    __tablename__ = "assets"

    __table_args__ = (
        UniqueConstraint(
            "facility_id",
            "asset_code",
            name="uq_asset_facility_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    facility_id: Mapped[int] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    asset_code: Mapped[str] = mapped_column(String(50), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(150), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ACTIVE"
    )

    installed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_life_years: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    facility = relationship("Facility", back_populates="assets")

    readings = relationship(
        "AssetReading",
        back_populates="asset",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    maintenance_records = relationship(
        "MaintenanceRecord",
        back_populates="asset",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

"""create_facilities_and_energy_readings_tables

Revision ID: 82c76d6c1fbd
Revises: 
Create Date: 2026-11-14 20:00:52.558196

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82c76d6c1fbd'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Create facilities and energy_readings tables."""
    # -------------------------------------------------------------------------
    # 1. Create 'facilities' table
    # -------------------------------------------------------------------------
    op.create_table(
        'facilities',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('building_type', sa.String(length=100), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_facilities_name'),
        'facilities',
        ['name'],
        unique=False,
    )
    op.create_index(
        op.f('ix_facilities_building_type'),
        'facilities',
        ['building_type'],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 2. Create 'energy_readings' table
    # -------------------------------------------------------------------------
    op.create_table(
        'energy_readings',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('facility_id', sa.Integer(), nullable=False),
        sa.Column('meter_id', sa.String(length=100), nullable=False),
        sa.Column('power_kw', sa.Float(), nullable=False),
        sa.Column('energy_kwh', sa.Float(), nullable=False),
        sa.Column('voltage_v', sa.Float(), nullable=True),
        sa.Column('current_a', sa.Float(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['facility_id'],
            ['facilities.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Single-column indexes
    op.create_index(
        op.f('ix_energy_readings_facility_id'),
        'energy_readings',
        ['facility_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_energy_readings_meter_id'),
        'energy_readings',
        ['meter_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_energy_readings_recorded_at'),
        'energy_readings',
        ['recorded_at'],
        unique=False,
    )
    # Composite indexes for high-frequency time-series queries
    op.create_index(
        'ix_energy_readings_facility_recorded_at',
        'energy_readings',
        ['facility_id', 'recorded_at'],
        unique=False,
    )
    op.create_index(
        'ix_energy_readings_meter_recorded_at',
        'energy_readings',
        ['meter_id', 'recorded_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema: Drop energy_readings and facilities tables."""
    # -------------------------------------------------------------------------
    # 1. Drop 'energy_readings' table and its indexes
    # -------------------------------------------------------------------------
    op.drop_index(
        'ix_energy_readings_meter_recorded_at',
        table_name='energy_readings',
    )
    op.drop_index(
        'ix_energy_readings_facility_recorded_at',
        table_name='energy_readings',
    )
    op.drop_index(
        op.f('ix_energy_readings_recorded_at'),
        table_name='energy_readings',
    )
    op.drop_index(
        op.f('ix_energy_readings_meter_id'),
        table_name='energy_readings',
    )
    op.drop_index(
        op.f('ix_energy_readings_facility_id'),
        table_name='energy_readings',
    )
    op.drop_table('energy_readings')

    # -------------------------------------------------------------------------
    # 2. Drop 'facilities' table and its indexes
    # -------------------------------------------------------------------------
    op.drop_index(
        op.f('ix_facilities_building_type'),
        table_name='facilities',
    )
    op.drop_index(
        op.f('ix_facilities_name'),
        table_name='facilities',
    )
    op.drop_table('facilities')


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel
from app.services import maintenance_ai_agent

from app.database.session import get_db
from app.agents.maintenance_agent import MaintenanceAgent
from app.models import Asset, Facility
from app.schemas.maintenance import WorkOrderCreate
from app.models import MaintenanceRecord
from app.schemas.maintenance import WorkOrderStatusUpdate


class MaintenanceAskRequest(BaseModel):
    question: str

router = APIRouter(
    prefix="/maintenance",
    tags=["Predictive Maintenance"],
)


@router.get("/facilities/{facility_id}/analyze")
def analyze_facility(
    facility_id: int,
    db: Session = Depends(get_db),
):
    facility = db.get(Facility, facility_id)

    if not facility:
        raise HTTPException(
            status_code=404,
            detail="Facility not found",
        )

    return MaintenanceAgent(db).analyze_facility(facility_id)


@router.get("/assets/{asset_id}/analyze")
def analyze_asset(
    asset_id: int,
    db: Session = Depends(get_db),
):
    asset = db.get(Asset, asset_id)

    if not asset:
        raise HTTPException(
            status_code=404,
            detail="Asset not found",
        )

    result = MaintenanceAgent(db).analyze_asset(asset_id)

    if "error" in result:
        raise HTTPException(
            status_code=422,
            detail=result["error"],
        )

    return result
@router.post("/assets/{asset_id}/work-orders", status_code=201)
def create_work_order(
    asset_id: int,
    payload: WorkOrderCreate,
    db: Session = Depends(get_db),
):
    asset = db.get(Asset, asset_id)

    if not asset:
        raise HTTPException(
            status_code=404,
            detail="Asset not found",
        )

    allowed_priorities = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    priority = payload.priority.upper()

    if priority not in allowed_priorities:
        raise HTTPException(
            status_code=422,
            detail="Priority must be LOW, MEDIUM, HIGH, or CRITICAL",
        )

    work_order = MaintenanceRecord(
        asset_id=asset_id,
        issue_type=payload.issue_type,
        description=payload.description,
        maintenance_date=payload.maintenance_date,
        status="SCHEDULED",
        priority=priority,
        source="MANUAL",
    )

    db.add(work_order)
    db.commit()
    db.refresh(work_order)

    return {
        "message": "Maintenance work order created successfully",
        "work_order_id": work_order.id,
        "asset_id": work_order.asset_id,
        "asset_code": asset.asset_code,
        "issue_type": work_order.issue_type,
        "description": work_order.description,
        "maintenance_date": (
            work_order.maintenance_date.isoformat()
            if work_order.maintenance_date else None
        ),
        "status": work_order.status,
        "priority": work_order.priority,
        "source": work_order.source,
    }
@router.get("/assets/{asset_id}/work-orders")
def get_asset_work_orders(
    asset_id: int,
    db: Session = Depends(get_db),
):
    asset = db.get(Asset, asset_id)

    if not asset:
        raise HTTPException(
            status_code=404,
            detail="Asset not found",
        )

    records = db.scalars(
        select(MaintenanceRecord)
        .where(MaintenanceRecord.asset_id == asset_id)
        .order_by(MaintenanceRecord.created_at.desc())
    ).all()

    return {
        "asset_id": asset.id,
        "asset_code": asset.asset_code,
        "total_work_orders": len(records),
        "work_orders": [
            {
                "work_order_id": record.id,
                "issue_type": record.issue_type,
                "description": record.description,
                "maintenance_date": (
                    record.maintenance_date.isoformat()
                    if record.maintenance_date else None
                ),
                "status": record.status,
                "priority": record.priority,
                "source": record.source,
            }
            for record in records
        ],
    }
@router.get("/facilities/{facility_id}/work-orders")
def get_facility_work_orders(
    facility_id: int,
    db: Session = Depends(get_db),
):
    facility = db.get(Facility, facility_id)

    if not facility:
        raise HTTPException(
            status_code=404,
            detail="Facility not found",
        )

    records = db.scalars(
        select(MaintenanceRecord)
        .join(Asset, MaintenanceRecord.asset_id == Asset.id)
        .where(Asset.facility_id == facility_id)
        .order_by(MaintenanceRecord.created_at.desc())
    ).all()

    return {
        "facility_id": facility.id,
        "facility_name": facility.name,
        "total_work_orders": len(records),
        "work_orders": [
            {
                "work_order_id": record.id,
                "asset_id": record.asset_id,
                "asset_code": record.asset.asset_code,
                "asset_name": record.asset.asset_name,
                "issue_type": record.issue_type,
                "description": record.description,
                "maintenance_date": (
                    record.maintenance_date.isoformat()
                    if record.maintenance_date else None
                ),
                "status": record.status,
                "priority": record.priority,
                "source": record.source,
            }
            for record in records
        ],
    }
@router.patch("/work-orders/{work_order_id}/status")
def update_work_order_status(
    work_order_id: int,
    payload: WorkOrderStatusUpdate,
    db: Session = Depends(get_db),
):
    work_order = db.get(MaintenanceRecord, work_order_id)

    if not work_order:
        raise HTTPException(
            status_code=404,
            detail="Work order not found",
        )

    work_order.status = payload.status

    db.commit()
    db.refresh(work_order)

    return {
        "message": "Work order status updated successfully",
        "work_order_id": work_order.id,
        "asset_id": work_order.asset_id,
        "status": work_order.status,
    }

@router.post("/facilities/{facility_id}/ask")
def ask_maintenance_agent(
    facility_id: int,
    body: MaintenanceAskRequest,
    db: Session = Depends(get_db),
):
    agent = MaintenanceAgent(db)

    analysis = agent.analyze_facility(facility_id)

    if "error" in analysis:
        raise HTTPException(status_code=404, detail=analysis["error"])

    context = maintenance_ai_agent.build_context(analysis)
    result = maintenance_ai_agent.answer(body.question, context)

    return {
        "facility_id": facility_id,
        "question": body.question,
        **result,
    }
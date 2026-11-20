"""
Main FastAPI application entry point.
"""

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.routes.energy import router as energy_router

from app.config import settings
from app.database import get_db

app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise Agentic FacilityOps AI Platform for Energy Intelligence & Monitoring",
    version="0.1.0",
    debug=settings.DEBUG,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(
    energy_router,
    prefix=settings.API_PREFIX,
)

@app.get("/", tags=["General"])
def root():
    """Root endpoint returning service status message."""
    return {"message": "Agentic FacilityOps AI Platform API is running"}


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint to verify service availability."""
    return {"status": "healthy"}


@app.get("/health/db", tags=["Health"])
def health_check_db(db: Session = Depends(get_db)):
    """
    Database connection test endpoint.
    Executes a lightweight query (SELECT 1) to verify PostgreSQL connectivity.
    """
    try:
        result = db.execute(text("SELECT 1")).scalar()
        return {
            "status": "connected",
            "database": "PostgreSQL",
            "check": "SELECT 1",
            "result": result,
            "message": "Database connection verified successfully",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "disconnected",
                "database": "PostgreSQL",
                "message": "Database connection failed",
                "error": str(exc),
            },
        )

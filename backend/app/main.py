"""SentinelOps Main FastAPI Application Factory."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.session import engine
from app.db.base import Base
from app.events.handlers import register_event_handlers
from app.jobs.scheduler import start_scheduler, shutdown_scheduler

# API Routers
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.machines import router as machines_router
from app.api.requests import router as requests_router
from app.api.approvals import router as approvals_router
from app.api.technicians import router as technicians_router
from app.api.verification import router as verification_router
from app.api.exceptions import router as exceptions_router
from app.api.inventory import router as inventory_router
from app.api.dashboard import router as dashboard_router
from app.api.audit import router as audit_router
from app.api.copilot import router as copilot_router
from app.api.integrations import router as integrations_router
from app.api.demo import router as demo_router
from app.api.tracker import router as tracker_router
from app.api.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    Base.metadata.create_all(bind=engine)
    register_event_handlers()
    start_scheduler()
    yield
    # Shutdown actions
    shutdown_scheduler()


app = FastAPI(
    title="SentinelOps Command Center API",
    description="Exception-First Service Command Center for Industrial Equipment.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving for evidence photos & proofs
upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")


# Health Check
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "system": "SentinelOps Command Center",
        "env": settings.APP_ENV,
        "demo_mode": settings.DEMO_MODE
    }


# Include all modular routers under /api
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(machines_router, prefix="/api")
app.include_router(requests_router, prefix="/api")
app.include_router(approvals_router, prefix="/api")
app.include_router(technicians_router, prefix="/api")
app.include_router(verification_router, prefix="/api")
app.include_router(exceptions_router, prefix="/api")
app.include_router(inventory_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(copilot_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")
app.include_router(demo_router, prefix="/api")
app.include_router(tracker_router, prefix="/api")
app.include_router(ws_router, prefix="/api")

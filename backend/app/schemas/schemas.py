"""Pydantic schemas for SentinelOps API requests and responses."""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# --- Auth ---
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    customer_id: Optional[int] = None
    telegram_chat_id: Optional[str] = None
    created_at: datetime


class UserCreate(BaseModel):
    email: str
    name: str
    role: str
    password: str
    customer_id: Optional[int] = None


# --- Machines ---
class MachineResponse(BaseModel):
    id: int
    code: str
    model: str
    serial: str
    site_id: int
    site_name: Optional[str] = None
    criticality: str
    status: str
    health_score: float
    contract_active: bool
    warranty_until: Optional[datetime] = None
    qr_token: str


# --- Service Requests ---
class RequestCreate(BaseModel):
    machine_id: int
    fault_category_id: int
    description: str
    priority: str = "MEDIUM"
    source: str = "WEB"


class SmartIntakeRequest(BaseModel):
    text: str


class ApproveRequest(BaseModel):
    plan_type: str = "BEST_FIT"  # FASTEST, BEST_FIT, LEAST_DISRUPTIVE
    safety_confirmed: bool = True
    technician_id: Optional[int] = None


class RejectRequest(BaseModel):
    reason: str


class HoldRequest(BaseModel):
    reason: str


class CancelRequest(BaseModel):
    reason: str


# --- Technician Actions ---
class CheckinRequest(BaseModel):
    lat: float
    lng: float


class StartWorkRequest(BaseModel):
    safety_confirmed: bool = True


class TaskLogCreate(BaseModel):
    note: str
    duration_minutes: int = 30


class EvidenceReviewRequest(BaseModel):
    status: str  # ACCEPTED, REJECTED
    reviewer_note: Optional[str] = None


# --- Hot-Swap & Exceptions ---
class HotSwapRequest(BaseModel):
    technician_id: int
    reason: Optional[str] = "Manager executed one-click Hot-Swap"


class ResolveExceptionRequest(BaseModel):
    resolution: str


# --- Inventory ---
class TransferCreate(BaseModel):
    item_id: int
    from_site_id: int
    to_site_id: int
    qty: int = 1


class PurchaseRequestCreate(BaseModel):
    item_id: int
    qty: int = 1
    reason: str
    lead_time_h: float = 48.0


# --- Copilot ---
class CopilotQueryRequest(BaseModel):
    message: str


# --- Integrations ---
class IoTWebhookPayload(BaseModel):
    machine_code: str
    metric: str
    value: float


# --- Demo ---
class FastForwardRequest(BaseModel):
    hours: float = 12.0

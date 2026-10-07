"""Database models for SentinelOps.
All types are DB-portable across SQLite and PostgreSQL.
"""
from datetime import datetime
from typing import Optional, List, Any
import json
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.db.base import Base
from app.core.time import utcnow


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    contact_email = Column(String(100), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    sites = relationship("Site", back_populates="customer", cascade="all, delete-orphan")
    users = relationship("User", back_populates="customer")


class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    access_notes = Column(Text, nullable=True)
    safety_requirements = Column(Text, nullable=True)
    geofence_radius_m = Column(Float, default=500.0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    customer = relationship("Customer", back_populates="sites")
    machines = relationship("Machine", back_populates="site")


class Machine(Base):
    __tablename__ = "machines"
    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    code = Column(String(50), unique=True, index=True, nullable=False)
    model = Column(String(100), nullable=False)
    serial = Column(String(100), unique=True, nullable=False)
    criticality = Column(String(20), default="MEDIUM", nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    status = Column(String(20), default="OPERATIONAL", nullable=False)  # OPERATIONAL, DEGRADED, DOWN
    warranty_until = Column(DateTime, nullable=True)
    contract_active = Column(Boolean, default=True, nullable=False)
    qr_token = Column(String(64), unique=True, index=True, nullable=False)
    installed_on = Column(DateTime, nullable=True)
    health_score = Column(Float, default=100.0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    site = relationship("Site", back_populates="machines")
    service_requests = relationship("ServiceRequest", back_populates="machine")
    sensor_readings = relationship("SensorReading", back_populates="machine")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    role = Column(String(30), nullable=False)  # ADMIN, MANAGER, SUPERVISOR, TECHNICIAN, CUSTOMER
    hashed_password = Column(String(255), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    telegram_chat_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    customer = relationship("Customer", back_populates="users")
    technician_profile = relationship("Technician", back_populates="user", uselist=False)
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


class Technician(Base):
    __tablename__ = "technicians"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    code = Column(String(50), unique=True, index=True, nullable=False)
    base_lat = Column(Float, nullable=False)
    base_lng = Column(Float, nullable=False)
    current_lat = Column(Float, nullable=False)
    current_lng = Column(Float, nullable=False)
    status = Column(String(20), default="AVAILABLE", nullable=False)  # AVAILABLE, BUSY, OFF_DUTY, UNAVAILABLE
    max_daily_jobs = Column(Integer, default=5, nullable=False)
    hourly_rate = Column(Float, default=50.0, nullable=False)
    rating = Column(Float, default=4.8, nullable=False)
    last_checkin = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="technician_profile")
    skills = relationship("TechnicianSkill", back_populates="technician", cascade="all, delete-orphan")
    certifications = relationship("TechnicianCertification", back_populates="technician", cascade="all, delete-orphan")
    assignments = relationship("Assignment", back_populates="technician")


class Skill(Base):
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class TechnicianSkill(Base):
    __tablename__ = "technician_skills"
    id = Column(Integer, primary_key=True, index=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False)
    level = Column(Integer, default=1, nullable=False)  # 1 to 5
    created_at = Column(DateTime, default=utcnow, nullable=False)

    technician = relationship("Technician", back_populates="skills")
    skill = relationship("Skill")


class TechnicianCertification(Base):
    __tablename__ = "technician_certifications"
    id = Column(Integer, primary_key=True, index=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)
    machine_model = Column(String(100), nullable=False)
    certified_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    technician = relationship("Technician", back_populates="certifications")


class FaultCategory(Base):
    __tablename__ = "fault_categories"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    expected_duration_h = Column(Float, default=2.0, nullable=False)
    priority_boost = Column(Integer, default=0, nullable=False)  # Boost priority by steps
    requires_certification = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    required_skills = relationship("FaultCategorySkill", back_populates="fault_category", cascade="all, delete-orphan")
    kit_items = relationship("KitItem", back_populates="fault_category", cascade="all, delete-orphan")
    evidence_templates = relationship("EvidenceTemplateItem", back_populates="fault_category", cascade="all, delete-orphan")


class FaultCategorySkill(Base):
    __tablename__ = "fault_category_skills"
    id = Column(Integer, primary_key=True, index=True)
    fault_category_id = Column(Integer, ForeignKey("fault_categories.id"), nullable=False)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False)
    min_level = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    fault_category = relationship("FaultCategory", back_populates="required_skills")
    skill = relationship("Skill")


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    kind = Column(String(30), default="PART", nullable=False)  # PART, TOOL, CONSUMABLE
    unit_cost = Column(Float, default=0.0, nullable=False)
    compat_group = Column(String(50), nullable=True)  # Used for finding substitutes
    created_at = Column(DateTime, default=utcnow, nullable=False)

    stock_levels = relationship("StockLevel", back_populates="item", cascade="all, delete-orphan")


class KitItem(Base):
    __tablename__ = "kit_items"
    id = Column(Integer, primary_key=True, index=True)
    fault_category_id = Column(Integer, ForeignKey("fault_categories.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
    kind = Column(String(30), default="PART", nullable=False)  # PART, TOOL, CONSUMABLE
    qty = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    fault_category = relationship("FaultCategory", back_populates="kit_items")
    item = relationship("InventoryItem")


class EvidenceTemplateItem(Base):
    __tablename__ = "evidence_template_items"
    id = Column(Integer, primary_key=True, index=True)
    fault_category_id = Column(Integer, ForeignKey("fault_categories.id"), nullable=False)
    key = Column(String(50), nullable=False)  # e.g., before_photo, after_photo, serial_check
    label = Column(String(150), nullable=False)
    type = Column(String(30), default="PHOTO", nullable=False)  # PHOTO, CHECKLIST, SERIAL, TEST_RESULT, SIGN_OFF, TEXT
    mandatory = Column(Boolean, default=True, nullable=False)
    who_submits = Column(String(30), default="TECHNICIAN", nullable=False)  # TECHNICIAN, SUPERVISOR, CUSTOMER
    created_at = Column(DateTime, default=utcnow, nullable=False)

    fault_category = relationship("FaultCategory", back_populates="evidence_templates")


class StockLevel(Base):
    __tablename__ = "stock_levels"
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
    location_type = Column(String(20), nullable=False)  # SITE, WAREHOUSE, VAN
    location_id = Column(Integer, nullable=False)  # site_id or technician_id or 0 for warehouse
    on_hand = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    min_level = Column(Integer, default=2, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    item = relationship("InventoryItem", back_populates="stock_levels")


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("service_requests.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
    qty = Column(Integer, default=1, nullable=False)
    source_location = Column(String(100), nullable=False)  # "Site A", "Site B (Transfer)", "Van T-07"
    source_type = Column(String(20), default="SITE", nullable=False)  # SITE, WAREHOUSE, VAN, TRANSFER
    source_location_id = Column(Integer, nullable=True)
    status = Column(String(30), default="RESERVED", nullable=False)  # RESERVED, IN_TRANSIT, ISSUED, RELEASED
    eta = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    item = relationship("InventoryItem")
    service_request = relationship("ServiceRequest", back_populates="reservations")


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
    qty = Column(Integer, default=1, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(30), default="DRAFT", nullable=False)  # DRAFT, SUBMITTED, APPROVED, ORDERED, RECEIVED
    lead_time_h = Column(Float, default=48.0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    item = relationship("InventoryItem")


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    raised_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    source = Column(String(20), default="WEB", nullable=False)  # WEB, QR, IOT, CHAT, PREVENTIVE
    fault_category_id = Column(Integer, ForeignKey("fault_categories.id"), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(20), default="MEDIUM", nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    effective_priority = Column(String(20), default="MEDIUM", nullable=False)
    priority_boost_reason = Column(Text, nullable=True)

    status = Column(String(30), default="CREATED", nullable=False)
    # CREATED, VALIDATED, PENDING_APPROVAL, APPROVED, ASSIGNED, IN_PROGRESS, COMPLETED, VERIFIED
    # ON_HOLD, EXCEPTION, REJECTED, CANCELLED

    response_due_at = Column(DateTime, nullable=True)
    sla_due_at = Column(DateTime, nullable=True)
    expected_duration_h = Column(Float, default=2.0, nullable=False)

    validation_report = Column(Text, nullable=True)  # JSON encoded string
    readiness_score = Column(Float, default=0.0, nullable=False)  # 0 to 100%
    risk_ratio = Column(Float, default=0.0, nullable=False)
    risk_level = Column(String(20), default="SAFE", nullable=False)  # SAFE, AT_RISK, CRITICAL, BREACHED

    safety_confirmed = Column(Boolean, default=False, nullable=False)
    track_token = Column(String(64), unique=True, index=True, nullable=False)
    hold_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)
    validated_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)

    machine = relationship("Machine", back_populates="service_requests")
    site = relationship("Site")
    user = relationship("User", foreign_keys=[raised_by])
    fault_category = relationship("FaultCategory")
    assignments = relationship("Assignment", back_populates="service_request", cascade="all, delete-orphan")
    reservations = relationship("Reservation", back_populates="service_request", cascade="all, delete-orphan")
    task_logs = relationship("TaskLog", back_populates="service_request", cascade="all, delete-orphan")
    evidence_items = relationship("EvidenceItem", back_populates="service_request", cascade="all, delete-orphan")
    exception_flags = relationship("ExceptionFlag", back_populates="service_request", cascade="all, delete-orphan")


class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("service_requests.id"), nullable=False)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)
    plan_type = Column(String(30), default="BEST_FIT", nullable=False)  # FASTEST, BEST_FIT, LEAST_DISRUPTIVE
    match_score = Column(Float, default=0.0, nullable=False)
    score_breakdown = Column(Text, nullable=True)  # JSON encoded string
    explanation = Column(Text, nullable=True)
    eta_minutes = Column(Float, default=30.0, nullable=False)
    status = Column(String(30), default="ASSIGNED", nullable=False)
    # ASSIGNED, ACKNOWLEDGED, DECLINED, NO_SHOW, REPLACED, COMPLETED
    ack_due_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    replaced_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    service_request = relationship("ServiceRequest", back_populates="assignments")
    technician = relationship("Technician", back_populates="assignments")


class TaskLog(Base):
    __tablename__ = "task_logs"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("service_requests.id"), nullable=False)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)
    note = Column(Text, nullable=False)
    duration_minutes = Column(Integer, default=30, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    service_request = relationship("ServiceRequest", back_populates="task_logs")
    technician = relationship("Technician")


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("service_requests.id"), nullable=False)
    template_key = Column(String(50), nullable=False)
    type = Column(String(30), default="PHOTO", nullable=False)
    file_url = Column(Text, nullable=True)
    text_value = Column(Text, nullable=True)
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    captured_at = Column(DateTime, default=utcnow, nullable=False)
    presence_status = Column(String(30), default="NOT_PROVIDED", nullable=False)
    # VERIFIED, OUTSIDE_GEOFENCE, NOT_PROVIDED
    status = Column(String(30), default="SUBMITTED", nullable=False)  # SUBMITTED, ACCEPTED, REJECTED
    reviewer_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    service_request = relationship("ServiceRequest", back_populates="evidence_items")
    submitter = relationship("User", foreign_keys=[submitted_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class ExceptionRule(Base):
    __tablename__ = "exception_rules"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    params = Column(Text, default="{}", nullable=False)  # JSON string
    actions = Column(Text, default="[]", nullable=False)  # JSON string
    escalate_to_role = Column(String(30), default="MANAGER", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class ExceptionFlag(Base):
    __tablename__ = "exception_flags"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("service_requests.id"), nullable=False)
    rule_code = Column(String(50), nullable=False)
    severity = Column(String(20), default="WARNING", nullable=False)  # INFO, WARNING, CRITICAL
    reason = Column(Text, nullable=False)
    blocker = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=True)
    owner_role = Column(String(30), default="MANAGER", nullable=False)
    status = Column(String(20), default="OPEN", nullable=False)  # OPEN, RESOLVED
    options_snapshot = Column(Text, nullable=True)  # JSON string
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    service_request = relationship("ServiceRequest", back_populates="exception_flags")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    level = Column(String(20), default="INFO", nullable=False)  # INFO, WARNING, CRITICAL
    link = Column(String(200), nullable=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="notifications")


class DomainEvent(Base):
    __tablename__ = "domain_events"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(100), index=True, nullable=False)
    payload = Column(Text, nullable=False)  # JSON string
    actor = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    seq = Column(Integer, unique=True, index=True, nullable=False)
    entity_type = Column(String(50), index=True, nullable=False)
    entity_id = Column(Integer, index=True, nullable=False)
    action = Column(String(100), nullable=False)
    actor_id = Column(Integer, nullable=True)
    actor_role = Column(String(50), nullable=False)
    before_state = Column(Text, nullable=True)  # JSON string
    after_state = Column(Text, nullable=True)   # JSON string
    meta = Column(Text, nullable=True)          # JSON string
    ts = Column(DateTime, default=utcnow, nullable=False)
    prev_hash = Column(String(64), nullable=False)
    hash = Column(String(64), nullable=False)


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    metric = Column(String(50), nullable=False)  # e.g., temperature, vibration, pressure
    value = Column(Float, nullable=False)
    ts = Column(DateTime, default=utcnow, nullable=False)

    machine = relationship("Machine", back_populates="sensor_readings")

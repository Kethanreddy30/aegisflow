import uuid
from typing import List, Literal, Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name       = Column(Text, nullable=False)
    slug       = Column(Text, unique=True, nullable=False)
    status     = Column(Text, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    providers  = relationship("TenantProvider", back_populates="tenant")
    policy     = relationship("TenantPolicy", uselist=False, back_populates="tenant")
    api_keys   = relationship("ApiKey", back_populates="tenant")


class TenantProvider(Base):
    __tablename__ = "tenant_providers"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id  = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    provider   = Column(Text, nullable=False)
    key_ref    = Column(Text, nullable=False)
    priority   = Column(Integer, default=1)
    rpm_limit  = Column(Integer, default=1000)
    tpm_limit  = Column(Integer, default=100000)
    status     = Column(Text, default="healthy")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Prevent same key_ref registered twice for same tenant
        __import__("sqlalchemy").UniqueConstraint(
            "tenant_id", "key_ref",
            name="uq_tenant_provider_key_ref"
        ),
    )

    tenant = relationship("Tenant", back_populates="providers")


class TenantPolicy(Base):
    __tablename__ = "tenant_policies"

    tenant_id          = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), primary_key=True)
    auto_failover      = Column(Boolean, default=True)
    notify_admin       = Column(Boolean, default=True)
    fallback_to_local  = Column(Boolean, default=True)
    budget_usd_monthly = Column(Numeric(10, 4), nullable=True)
    masking_enabled    = Column(Boolean, default=True)
    allowed_models     = Column(ARRAY(Text), default=[])
    fallback_model     = Column(Text, nullable=True)

    tenant = relationship("Tenant", back_populates="policy")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id  = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    event_type = Column(Text, nullable=False)
    payload    = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Efficient per-tenant audit queries sorted by time
        Index("ix_audit_log_tenant_created", "tenant_id", "created_at"),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    # key_hash is PRIMARY KEY — PostgreSQL automatically indexes it
    key_hash     = Column(Text, primary_key=True)
    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    label        = Column(Text, nullable=True)
    status       = Column(Text, default="active")
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="api_keys")


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class ProviderKeySchema(BaseModel):
    key_id:    str
    provider:  Literal["openai", "anthropic", "deepseek", "ollama"]
    key_ref:   str
    priority:  int = 1
    rpm_limit: int = 1000
    status:    Literal["healthy", "degraded", "exhausted", "disabled"] = "healthy"


class FailoverPolicySchema(BaseModel):
    automatic:          bool            = True
    notify_admin:       bool            = True
    fallback_to_local:  bool            = True
    budget_usd_monthly: Optional[float] = None
    fallback_model:     Optional[str]   = None


class TenantConfigSchema(BaseModel):
    tenant_id:       uuid.UUID
    slug:            str
    providers:       List[ProviderKeySchema]
    policy:          FailoverPolicySchema
    masking_enabled: bool      = True
    allowed_models:  List[str] = []


class TenantCreateRequest(BaseModel):
    name: str
    slug: str
    masking_enabled: bool = True


class TenantCreateResponse(BaseModel):
    tenant_id: uuid.UUID
    slug:      str
    api_key:   str


class ProviderRegisterRequest(BaseModel):
    provider:  Literal["openai", "anthropic", "deepseek", "ollama"]
    key_ref:   str
    priority:  int = 1
    rpm_limit: int = 1000


class PolicyUpdateRequest(BaseModel):
    auto_failover:      Optional[bool]      = None
    notify_admin:       Optional[bool]      = None
    fallback_to_local:  Optional[bool]      = None
    budget_usd_monthly: Optional[float]     = None
    allowed_models:     Optional[List[str]] = None
    fallback_model:     Optional[str]       = None

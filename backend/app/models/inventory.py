from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import InventoryRequestStatus, InventoryRequestType, VehicleStatus


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint("organization_id", "vin"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    stock_number: Mapped[str | None] = mapped_column(String(50))  # e.g. "124"
    vin: Mapped[str] = mapped_column(String(32), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str | None] = mapped_column(String(50))
    trim: Mapped[str | None] = mapped_column(String(100))
    mileage: Mapped[int | None] = mapped_column(Integer)
    purchase_price: Mapped[int | None] = mapped_column(Integer)
    sale_price: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), default="IRR")
    # Rich catalog details (ads, branch handoff, import)
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    body_type: Mapped[str | None] = mapped_column(String(50))
    transmission: Mapped[str | None] = mapped_column(String(50))
    fuel_type: Mapped[str | None] = mapped_column(String(50))
    engine: Mapped[str | None] = mapped_column(String(80))
    plate_number: Mapped[str | None] = mapped_column(String(40))
    doors: Mapped[int | None] = mapped_column(Integer)
    seats: Mapped[int | None] = mapped_column(Integer)
    options: Mapped[str | None] = mapped_column(Text)  # free-text / comma list
    exterior_condition: Mapped[str | None] = mapped_column(String(80))
    interior_condition: Mapped[str | None] = mapped_column(String(80))
    import_source: Mapped[str | None] = mapped_column(String(120))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[VehicleStatus] = mapped_column(
        Enum(VehicleStatus, name="vehicle_status"), default=VehicleStatus.IN_STOCK
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    history: Mapped[list[VehicleHistory]] = relationship(back_populates="vehicle")
    branch_links: Mapped[list[VehicleBranch]] = relationship(back_populates="vehicle")


class VehicleHistory(Base):
    __tablename__ = "vehicle_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    from_status: Mapped[VehicleStatus | None] = mapped_column(
        Enum(VehicleStatus, name="vehicle_status", create_constraint=False)
    )
    to_status: Mapped[VehicleStatus] = mapped_column(
        Enum(VehicleStatus, name="vehicle_status", create_constraint=False), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vehicle: Mapped[Vehicle] = relationship(back_populates="history")


class VehicleBranch(Base):
    """Tracks which branches hold or have interest in a vehicle."""

    __tablename__ = "vehicle_branches"
    __table_args__ = (UniqueConstraint("vehicle_id", "branch_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), nullable=False)
    is_primary: Mapped[bool] = mapped_column(default=True)
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vehicle: Mapped[Vehicle] = relationship(back_populates="branch_links")


class InventoryRequest(Base):
    __tablename__ = "inventory_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    requesting_branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), nullable=False)
    target_branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    request_type: Mapped[InventoryRequestType] = mapped_column(
        Enum(InventoryRequestType, name="inventory_request_type"),
        default=InventoryRequestType.GENERAL,
    )
    status: Mapped[InventoryRequestStatus] = mapped_column(
        Enum(InventoryRequestStatus, name="inventory_request_status"),
        default=InventoryRequestStatus.OPEN,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_items.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

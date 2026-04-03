from sqlalchemy import Boolean, Column, Integer, String, ForeignKey
from .database import Base


class SimulationState(Base):
    """One row per tenant — tracks the factory's current simulated day."""
    __tablename__ = "simulation_state"

    tenant_id = Column(String, primary_key=True, index=True)
    current_day = Column(Integer, default=1, nullable=False)


class WorkOrder(Base):
    """A customer order for a custom electric go-kart."""
    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, index=True, nullable=False)
    frame_type = Column(String, nullable=False)
    motor_type = Column(String, nullable=False)
    battery = Column(String, nullable=False)
    finish = Column(String, nullable=False)
    status = Column(String, default="open", nullable=False)
    created_day = Column(Integer, nullable=False)


class Operation(Base):
    """A single manufacturing step belonging to a work order."""
    __tablename__ = "operations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, index=True, nullable=False)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False)
    name = Column(String, nullable=False)
    work_center = Column(String, nullable=False)
    duration_days = Column(Integer, nullable=False)
    scheduled_start_day = Column(Integer, nullable=True)
    scheduled_end_day = Column(Integer, nullable=True)
    # Statuses: planned → ready → awaiting_completion → complete
    status = Column(String, default="planned", nullable=False)
    # Plain integer FK — avoids SQLAlchemy relationship complexity for self-referential deps
    depends_on_operation_id = Column(Integer, nullable=True)
    # Tracks how many rework loops have been applied (capped at 1)
    rework_count = Column(Integer, default=0, nullable=False)


class InventoryItem(Base):
    """A part type available for use in work orders."""
    __tablename__ = "inventory_items"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String, nullable=False)
    category   = Column(String, nullable=False)   # frame | motor | battery | finish
    deprecated = Column(Boolean, default=False, nullable=False)
    requires_pre_assembly_test = Column(Boolean, default=False, nullable=False)
    receive_duration_days      = Column(Integer, nullable=True)  # motors only
    qty_on_hand                = Column(Integer, nullable=True)  # None = infinite (finishes)

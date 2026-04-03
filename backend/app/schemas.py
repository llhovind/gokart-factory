from __future__ import annotations
from pydantic import BaseModel, ConfigDict


class WorkOrderCreate(BaseModel):
    frame_type: str
    motor_type: str
    battery: str
    finish: str


class AdvanceRequest(BaseModel):
    days: int | None = None
    mode: str | None = None  # "next_event"


class InitResponse(BaseModel):
    token: str


class SimulationStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: str
    current_day: int


class WorkOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    frame_type: str
    motor_type: str
    battery: str
    finish: str
    status: str
    created_day: int


class InventoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    deprecated: bool
    requires_pre_assembly_test: bool
    receive_duration_days: int | None
    qty_on_hand: int | None


class InventoryResponse(BaseModel):
    frame: list[InventoryItemOut]
    motor: list[InventoryItemOut]
    battery: list[InventoryItemOut]
    finish: list[InventoryItemOut]


class OperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    work_order_id: int
    name: str
    work_center: str
    duration_days: int
    scheduled_start_day: int | None
    scheduled_end_day: int | None
    status: str
    depends_on_operation_id: int | None
    rework_count: int

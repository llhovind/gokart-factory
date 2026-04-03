"""
FastAPI application entry point.

In development:  uvicorn app.main:app --reload  (run from backend/)
In production:   uvicorn app.main:app --host 0.0.0.0 --port 8000
                 (frontend/dist must exist — built by `npm run build`)
"""
import os
import pathlib
import uuid

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .auth import create_token, get_current_tenant_id
from .database import Base, SessionLocal, engine, get_db
from .models import InventoryItem, Operation, SimulationState, WorkOrder
from .schemas import (
    AdvanceRequest,
    InitResponse,
    InventoryResponse,
    OperationOut,
    SimulationStateOut,
    WorkOrderCreate,
    WorkOrderOut,
)
from . import services

app = FastAPI(title="Gokart Factory")

# CORS — only relevant when Vite dev server (5173) calls FastAPI (8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        services.seed_inventory(db)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Auth / Init
# ---------------------------------------------------------------------------

@app.post("/api/init", response_model=InitResponse)
def init(db: Session = Depends(get_db)):
    """
    Generate a new anonymous tenant. Call once when the app loads; the returned
    JWT is stored in localStorage and sent on every subsequent request.
    """
    tenant_id = str(uuid.uuid4())
    db.add(SimulationState(tenant_id=tenant_id, current_day=1))
    db.commit()
    return InitResponse(token=create_token(tenant_id))


# ---------------------------------------------------------------------------
# Simulation state
# ---------------------------------------------------------------------------

@app.get("/api/simulation/state", response_model=SimulationStateOut)
def get_simulation_state(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    sim = db.query(SimulationState).filter_by(tenant_id=tenant_id).first()
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation state not found")
    return sim


@app.post("/api/simulation/advance", response_model=SimulationStateOut)
def advance_simulation(
    req: AdvanceRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    return services.advance_simulation(db, tenant_id, req.days, req.mode)


# ---------------------------------------------------------------------------
# Work orders
# ---------------------------------------------------------------------------

@app.post("/api/workorders", response_model=WorkOrderOut)
def create_workorder(
    data: WorkOrderCreate,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    sim = db.query(SimulationState).filter_by(tenant_id=tenant_id).first()
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation state not found")
    return services.create_work_order_with_operations(db, tenant_id, data, sim.current_day)


@app.get("/api/workorders", response_model=list[WorkOrderOut])
def list_workorders(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    return db.query(WorkOrder).filter_by(tenant_id=tenant_id).all()


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

@app.get("/api/operations", response_model=list[OperationOut])
def list_all_operations(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """All operations for this tenant, sorted by scheduled start day."""
    return (
        db.query(Operation)
        .filter_by(tenant_id=tenant_id)
        .order_by(Operation.scheduled_start_day)
        .all()
    )


@app.get("/api/workcenters/{name}/operations", response_model=list[OperationOut])
def get_workcenter_operations(
    name: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    return (
        db.query(Operation)
        .filter(Operation.tenant_id == tenant_id, Operation.work_center == name)
        .order_by(Operation.scheduled_start_day)
        .all()
    )


@app.post("/api/operations/{op_id}/complete", response_model=OperationOut)
def complete_operation(
    op_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    return services.complete_operation(db, op_id, tenant_id)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@app.get("/api/inventory", response_model=InventoryResponse)
def get_inventory(db: Session = Depends(get_db)):
    """Non-deprecated inventory items grouped by category. No auth required."""
    items = db.query(InventoryItem).filter_by(deprecated=False).all()
    grouped: dict[str, list] = {"frame": [], "motor": [], "battery": [], "finish": []}
    for item in items:
        grouped[item.category].append(item)
    return grouped


# ---------------------------------------------------------------------------
# Static file serving — production only
# Mount AFTER all /api routes so the catch-all doesn't swallow API calls.
# ---------------------------------------------------------------------------

# Allow override via env var for Docker path alignment
_DIST_ENV = os.environ.get("FRONTEND_DIST_PATH")
if _DIST_ENV:
    STATIC_DIR = pathlib.Path(_DIST_ENV)
else:
    # Local layout:  backend/app/main.py → ../../frontend/dist
    STATIC_DIR = pathlib.Path(__file__).parent.parent.parent / "frontend" / "dist"

if STATIC_DIR.exists():
    # Serve hashed JS/CSS assets (Vite puts them in /assets/)
    _assets_dir = STATIC_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        """Catch-all: return index.html so Vue Router handles client-side navigation."""
        return FileResponse(str(STATIC_DIR / "index.html"))

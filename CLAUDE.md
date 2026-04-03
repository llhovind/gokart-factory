# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API docs at `http://localhost:8000/docs`. The SQLite DB (`gokart.db`) is created automatically on first startup via `Base.metadata.create_all()` — no migrations needed.

### Frontend
```bash
cd frontend
npm install
npm run dev     # http://localhost:5173 — proxies /api → localhost:8000
npm run build   # outputs to frontend/dist/
```

### Production
```bash
docker compose up --build   # http://localhost:8000
```

## Architecture

### Multi-tenancy
Every browser session gets a UUID `tenant_id` embedded in a JWT (stored in `localStorage`). `POST /api/init` creates both the JWT and a `SimulationState` row. Every DB query filters by `tenant_id`. The JWT dependency (`auth.get_current_tenant_id`) is injected into every protected route.

### Request flow
Frontend `api.js` → axios interceptor attaches `Authorization: Bearer <token>` → FastAPI route → `get_current_tenant_id` dependency decodes JWT → service function queries DB filtered by `tenant_id`.

### Work order → operations pipeline (`services.py`)
Creating a work order triggers a fixed sequence: insert `WorkOrder` → generate 10 `Operation` rows → flush to get IDs → wire `depends_on_operation_id` by name (second pass) → call `scheduler.reschedule_all()` → commit. The two-flush pattern is necessary because dependency wiring requires IDs that only exist after the first flush.

### Scheduling (`scheduler.py`)
Pure function — no DB access. Takes a list of Operation ORM objects, runs Kahn's BFS topological sort on `depends_on_operation_id`, then assigns `scheduled_start_day` / `scheduled_end_day` respecting work center capacity (`Assembly: 2/day`, `Inspection: 2/day`, `Finishing: 1/day`, others unlimited). Called on initial work order creation and again after any rework insertion.

### Inspection rework logic (`services.complete_operation`)
When "Frame Stress Test" or "Motor Torque Test" is completed, a deterministic result is computed via `hashlib.md5(f"{work_order_id}{op_name}".encode())`. **Do not use Python's `hash()` — it's non-deterministic across restarts.** If the result is below threshold and `rework_count < 1`, two new operations are inserted (Rework + Retest), the downstream op's `depends_on_operation_id` is rewired to point to the Retest op, and `reschedule_all` is re-run on all non-complete ops for the tenant.

### Static file serving
In production, FastAPI mounts `frontend/dist/assets/` at `/assets` and serves `index.html` as a catch-all for all other non-`/api` routes. **API routes must be registered before the catch-all `/{full_path:path}` route** — FastAPI matches in registration order. The `STATIC_DIR.exists()` guard lets the backend start in dev without a built frontend. Path is overridable via `FRONTEND_DIST_PATH` env var (used in Docker).

### Pinia stores (`stores.js`)
Three stores: `useAuthStore` (JWT lifecycle), `useSimStore` (current day), `useOpsStore` (work orders + operations). `authStore.init()` must complete before any other authenticated request — sequenced explicitly in `App.vue`'s `onMounted`.

### Extra endpoints not in the original spec
- `GET /api/simulation/state` — needed by `simStore.fetchState()` on page load
- `GET /api/operations` — returns all tenant ops sorted by start day, used by `OperationTable.vue`

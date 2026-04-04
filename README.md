# GoKart Factory

A manufacturing simulation for a custom electric go-kart factory.

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Frontend**: Vue 3 + Vite + Pinia + Tailwind CSS
- **Auth**: Anonymous tenants via JWT (one per browser session)

---

## Local Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API available at `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App available at `http://localhost:5173` (proxies `/api` → FastAPI)

---

## Production (Docker)

```bash
docker compose up --build
```

App available at `http://localhost:8000`

The multi-stage Dockerfile builds the Vue frontend, then serves it via FastAPI's static file middleware.

SQLite database is persisted to `./data/gokart.db` via a Docker volume.

---

## How It Works

1. **On first load** — the frontend calls `POST /api/init` to create an anonymous tenant and stores the JWT in `localStorage`.
2. **Create a Work Order** — pick frame, motor, battery, and finish options. The backend expands this into 10 manufacturing operations and schedules them.
3. **Advance time** — use the +1 Day, +5 Days, or "Next Event" buttons to move the factory clock forward. Operations transition: `planned → ready → awaiting_completion`.
4. **Complete operations** — go to the Work Centers tab and click "Complete" on any `Awaiting` operation. Inspection operations run a deterministic failure check; failures insert a rework + retest pair and reschedule.
5. **View timelines** — the Work Order Timeline shows per-order operation schedules; the Factory Timeline displays a Gantt chart of all work orders across work centers.

---

## Project Structure

```
gokart-factory/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app, routes, static file serving
│   │   ├── database.py    # SQLAlchemy engine + session
│   │   ├── models.py      # ORM models (SimulationState, WorkOrder, Operation)
│   │   ├── schemas.py     # Pydantic request/response models
│   │   ├── services.py    # Business logic
│   │   ├── scheduler.py   # Capacity-aware dependency scheduling
│   │   └── auth.py        # JWT generation and validation
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.vue
│   │   ├── api.js         # Axios + JWT interceptor
│   │   ├── stores.js      # Pinia: auth, sim, ops
│   │   └── components/
│   │       ├── SimulationControls.vue
│   │       ├── WorkOrderCreator.vue
│   │       ├── WorkCenterView.vue
│   │       ├── OperationTable.vue
│   │       ├── WorkOrderTimeline.vue
│   │       ├── FactoryTimeline.vue
│   │       └── StatusBadge.vue
│   └── ...
├── Dockerfile
└── docker-compose.yml
```

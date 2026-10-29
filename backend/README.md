# CE 725 Backend

Python 3.12 • FastAPI • SQLAlchemy 2.0 • Pydantic v2.

## First-time setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
```

## Dev commands

```powershell
# Run the API
uvicorn api.main:app --reload

# Tests
pytest -q

# Lint
ruff check .
```

## Layout

```
backend/
├── boq_engine/      # Pure engine (geometry, sizing, take-off, pricing, trace)
├── api/
│   ├── main.py      # FastAPI app
│   ├── db/          # SQLAlchemy models + session
│   ├── schemas/     # Pydantic I/O schemas
│   ├── routes/      # (Week 5+) HTTP routes
│   └── services/    # (Week 4+) rate import, search, agent runner
├── agents/          # (Week 8+) Claude agents
├── alembic/         # DB migrations
├── data/            # DSR PDFs, reference estimates
└── tests/           # pytest suite
```

See [compiled-yawning-grove.md](../../../../.claude/plans/compiled-yawning-grove.md) for the 24-week plan.

# CE 725 Project — AI-Assisted BOQ and Cost Estimation

Course project for CE 725. A web app that turns a short building brief into a priced bill of quantities (BOQ) + element-wise cost estimate, with every number traceable to code or a versioned CPWD DSR rate table.

See [the full 24-week plan](../../.claude/plans/compiled-yawning-grove.md) and the PDR in `docs/`.

## Layout

```
CE725Project/
├── backend/     # Python 3.12+, FastAPI, SQLAlchemy, pure engine
├── frontend/    # Next.js 15 (TS, Tailwind, shadcn/ui)
└── docs/
```

## First-time setup

### Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
pytest -q
uvicorn api.main:app --reload
```

### Frontend
```powershell
cd frontend
npm install
npm run dev
```

API docs live at http://localhost:8000/docs; UI at http://localhost:3000.

## Phase status

- [x] Phase 1 Week 1 — Repo bootstrap + data model
- [ ] Phase 1 Week 2 — Engine: geometry + sizing
- [ ] Phase 1 Week 3 — Engine: take-off + pricing
- [ ] Phase 1 Week 4 — DSR import + Gate 1
- [ ] Phase 2 (W5–10) — API, UI, mapping agent, Gate 2
- [ ] Phase 3 (W11–16) — Agents + reports, Gate 3
- [ ] Phase 4 (W17–24) — Beta infra, pilot, Gate 4

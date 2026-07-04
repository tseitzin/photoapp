# Aperture — Photo Organizer (project rules)

Local-first photo library organizer. Vue 3 + FastAPI + PostgreSQL. Single user,
local only, **no authentication** — the duplicate_decisions table tracks review
choices, not accounts. Read docs/ARCHITECTURE.md before structural changes;
track progress in TASKS.md.

## Fixed ports (this machine)

- Backend: **8003** (Buddy=8000, VaultKeeper=8001, Bible=8002, InboxKeeper=8010)
- Postgres: Docker host port **5435** (5432=native PG, 5433=VaultKeeper, 5434=Buddy)
- Frontend: 5173

## Commands

```bash
docker compose up -d                          # Postgres
cd backend && source .venv/bin/activate
  pip install -r requirements.txt -r requirements-dev.txt
  alembic upgrade head
  uvicorn app.main:app --port 8003 --reload
  pytest                                      # tests
  ruff check . && ruff format --check . && mypy app   # lint/type
cd frontend
  npm install && npm run dev
  npm run test && npm run lint && npm run type-check
```

## Hard rules

- **Never modify `design_handoff_photo_organizer/`** — it is the read-only visual
  source of truth. Recreate as Vue SFCs; do not port support.js or .dc.html markup.
- Preserve the design's visual language (tokens, spacing, radii, light/dark palettes
  from the handoff README). No CSS frameworks or component libraries.
- Originals are read-only: the app never moves/modifies photos except via the
  audited quarantine workflow in `backend/app/files/`.
- Tests never touch a real photo library — temp dirs + generated images only.
- **PostgreSQL, not SQLite** — deliberate stack-consistency choice; don't revisit.
- Destructive file operations: quarantine-first, explicit confirmation, audit log,
  path-containment validation. Tests before UI.

## Conventions

- Surgical, incremental changes; PRs of 300–600 lines — split anything bigger.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Behavior-named tests (describe the behavior, not the function).
- Type hints throughout Python; TypeScript types throughout the frontend.
- Layering: api → services → repositories; routers hold no business logic; only
  repositories query the DB; components call the typed api/ client, never fetch.
- Config via environment (pydantic-settings); nothing hard-coded.
- Communication: direct, no progress play-by-play.

## Deployment

None — local development only. Postgres via `docker compose up -d`; frontend and
backend run natively on the Mac.

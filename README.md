# Aperture — Photo Organizer

A local-first web application for organizing and searching a personal photo library
(tens to hundreds of thousands of images). Photos are **indexed in place** — originals
are never moved or modified. The app provides browsing, metadata search/filtering,
exact and near-duplicate detection, and a quarantine-first safe-deletion workflow.

**Status: Phase 1 (planning) complete.** No application code exists yet — see
[TASKS.md](TASKS.md) for the implementation plan and current progress.

The visual design lives in [`design_handoff_photo_organizer/`](design_handoff_photo_organizer/)
(HTML prototypes + screenshots + handoff spec). It is the source of truth for look and
behavior and must not be modified; the prototypes are recreated as Vue 3 components.

## What it does

- Index photos from one or more configured directories on this Mac, in place.
- Browse a fast, virtualized thumbnail grid grouped by folder / date / camera, with filtering.
- View any photo full-screen with metadata and keyboard navigation.
- Find exact duplicates (SHA-256) and visually similar photos (perceptual hash + LSH).
- Review duplicate groups and record keep/remove decisions.
- Quarantine (never silently delete) unwanted files, with audit log and restore.
- Track scan progress and errors.

## Architecture

Vue 3 SPA → FastAPI backend → PostgreSQL (Docker). Full detail, including the
duplicate-detection design and safety model: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```
frontend (Vue 3 + Vite + TS)  ──HTTP──▶  backend (FastAPI, :8003)  ──▶  PostgreSQL (Docker, :5435)
                                              │
                                              ├─▶ photo roots (read-only indexing)
                                              ├─▶ thumbnail cache (app-managed)
                                              └─▶ quarantine dir (safe deletion)
```

### Ports (fixed for this machine — see CLAUDE.md)

| Service | Port | Note |
|---|---|---|
| FastAPI backend | **8003** | Buddy=8000, VaultKeeper=8001, Bible=8002, InboxKeeper=8010 |
| Vite dev server | 5173 | |
| PostgreSQL (Docker) | **5435** | 5432 = native Postgres, 5433/5434 = other projects |

## Prerequisites

- macOS with Docker Desktop
- Python 3.12+
- Node 20+
- Git

## Setup

> Commands below are the target workflow; they become functional in Phase 2.

```bash
# 1. Database
docker compose up -d

# 2. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env          # then review values
alembic upgrade head
uvicorn app.main:app --port 8003 --reload

# 3. Frontend (separate terminal)
cd frontend
npm install
cp .env.example .env
npm run dev                   # http://localhost:5173
```

## Testing

```bash
cd backend && pytest                 # backend unit + API tests
cd frontend && npm run test          # vitest component/store tests
cd frontend && npm run lint && npm run type-check
```

Tests use temporary directories and generated images only — they must never touch a
real photo library.

## Environment variables

Documented in `backend/.env.example` and `frontend/.env.example` (created in Phase 2).
Key values:

| Variable | Purpose | Example |
|---|---|---|
| `DATABASE_URL` | Postgres connection | `postgresql+psycopg://aperture:aperture@localhost:5435/aperture` |
| `THUMBNAIL_CACHE_DIR` | App-managed thumbnail cache | `~/.aperture/thumbnails` |
| `QUARANTINE_DIR` | Where "deleted" files are moved | `~/.aperture/quarantine` |
| `VITE_API_BASE_URL` | Backend URL for the frontend | `http://localhost:8003` |

No secrets exist in this app; `.env` files are still git-ignored on principle.

## How scanning works

Scans walk configured root directories, skip symlinked directories (cycle safety),
record per-file errors without aborting, and process each image in a single I/O pass:
read bytes → SHA-256 → decode → dimensions + EXIF + perceptual hash + thumbnail.
Unchanged files (same size + mtime) are skipped on rescan; missing files are flagged,
not purged. Scan state persists in the DB, so scans are resumable and progress is
pollable by the UI.

## Deletion safety model

- Nothing is ever deleted automatically.
- "Delete" means **move to the quarantine directory**, preserving relative path.
- Every file operation is validated to resolve inside an approved photo root
  (realpath containment — no traversal, no symlink escape) and written to an audit log.
- Restore-from-quarantine is a first-class operation.
- Permanent deletion only acts on quarantined files, as a separate explicit action.

## Generated data locations

- Thumbnails: `THUMBNAIL_CACHE_DIR` — deletable and rebuildable at any time.
- Quarantine: `QUARANTINE_DIR` — contains real photos; not managed as cache.
- Neither is committed to git.

## Limitations (v1)

- **RAW files are not supported** (no decode/thumbnail/pHash). The design shows RAW
  badges; support via `rawpy` is a future consideration.
- HEIC/HEIF depends on `pillow-heif`.
- Group-by-location is deferred (needs GPS EXIF + reverse geocoding).
- Perceptual hashing finds resized/recompressed variants, not crops or edits —
  image-embedding search (pgvector) is the planned upgrade path.
- Single user, local only, no authentication. Do not expose the backend beyond localhost.
- The Organize (move/tag/rename) flow from the design is deferred to Phase 7.

## Skills

| Area | Choice |
|---|---|
| Frontend | Vue 3 (Composition API), TypeScript, Vite, Vue Router, Pinia |
| Styling | Hand-rolled CSS on custom properties (design tokens); no CSS framework |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic |
| Database | PostgreSQL 16 (`pgvector/pgvector:pg16` image; extension available for future embeddings) |
| Imaging | Pillow, pillow-heif, ImageHash |
| Infrastructure | Docker Compose (Postgres only); frontend/backend run natively |
| Testing | pytest (backend), Vitest (frontend) |
| CI/CD | None yet (local-only project) |

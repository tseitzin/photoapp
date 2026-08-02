# Aperture — Photo Organizer

A local-first web application for organizing and searching a personal photo library
(tens to hundreds of thousands of images). Photos are **indexed in place** — originals
are never moved or modified except through two explicit, audited file workflows:
**quarantine** (safe deletion) and **organize** (physical moves to a new folder structure).
The app provides browsing by folder/date/camera, metadata search/filtering, exact and
near-duplicate detection, and a safe-deletion workflow with full audit history.

**Status: Phases 1–7 complete.** Core features shipping: incremental scanning with
live progress, full library browsing (grid, folders, filters, search, lightbox),
exact SHA-256 duplicate detection + near-duplicates via perceptual hash (LSH-banded)
with pair-by-pair review, safe quarantine-first file management with audit log,
physical organize (move folders to a new structure by date/camera/keep, with optional
rename), and GPS coordinate extraction (UI planned). See [TASKS.md](TASKS.md) for
roadmap.

The visual design lives in [`design_handoff_photo_organizer/`](design_handoff_photo_organizer/)
(HTML prototypes + design spec) and is **read-only** — the source of truth for look and
behavior. Vue 3 components recreate the design; the handoff files must never be modified.

## What it does

- **Index**: Scan one or more configured folders on this Mac, with incremental rescan
  (unchanged files skipped by size+mtime; moves detected by SHA-256).
- **Browse**: Fast thumbnail grid grouped by folder / date / camera, with filtering
  by metadata, filename search, and sort. Click a folder name to filter the grid.
  Full-screen lightbox with instant thumbnail + debounced 2048px preview.
- **Select in bulk**: Click a photo to select it, **Shift+click** to select the whole
  run between the two, **⌘/Ctrl+click** to add or remove one. A selection bar shows
  the count and can mark or unmark the whole set for deletion in one call. Selection
  is scoped to the loaded page and clears whenever the grid refetches.
- **Find duplicates**: Exact duplicates (SHA-256) and visually similar photos (perceptual
  hash + LSH). Side-by-side compare and record keep/remove decisions.
- **Organize**: Physically move selected folders' photos into a destination with
  structure options (keep existing folders, by date `YYYY/MM/`, by camera model),
  optional rename to `YYYY-MM-DD_HHMMSS.ext`, skip-duplicates toggle. Dry-run
  preview matches the execute plan exactly.
- **Quarantine**: Mark unwanted photos for deletion → move to quarantine folder
  (reversible, preserves source path) → permanent delete behind typed confirmation.
- **Track**: Scan progress/errors with resumable job state; audit log of all
  file operations; lifetime deletion stats.

## Architecture

Aperture is a three-tier SPA: Vue 3 frontend (Composition API + TypeScript) makes
HTTP calls to a FastAPI backend (strict layering: routers → services → repositories)
which queries PostgreSQL and manages files on disk. Scanning and organizing run as
background jobs using an in-process job runner with persistent DB state (resumable,
pollable by the UI). Thumbnails and previews are content-addressed by photo SHA-256;
the quarantine folder and thumbnail cache are app-managed and deletable.

```mermaid
flowchart TD
    subgraph Browser["Browser — Vue 3 SPA (:5173)"]
        V["Views<br/>(Home · Library · Duplicates ·<br/>Organize · Scan · Cleanup)"]
        ST["Pinia stores"]
        AC["Typed API client"]
        V --> ST --> AC
    end

    subgraph Backend["FastAPI backend (:8003)"]
        API["api/ — thin routers"]
        SVC["services/ — use-cases,<br/>transactions"]
        REPO["repositories/ — all DB queries"]
        JOBS["jobs/ — background runner<br/>(scans & organize, serialized)"]
        SCAN["scanner/ + dedupe/<br/>walk · EXIF · SHA-256 · pHash"]
        FILES["files/ — path safety,<br/>quarantine & organize moves"]
        API --> SVC --> REPO
        SVC --> JOBS
        JOBS --> SCAN
        SVC --> FILES
    end

    subgraph DB["PostgreSQL 16 (:5435, Docker)"]
        TBL[("photos · scans · scan_roots<br/>duplicate_groups + decisions<br/>file_operations · organize_runs")]
    end

    subgraph FS["Filesystem"]
        ROOTS["Photo roots<br/>(read-only to app)"]
        THUMB["Thumbnail cache<br/>(sha256-keyed, rebuildable)"]
        QUAR["Quarantine dir<br/>(reversible deletions)"]
    end

    AC -- "HTTP/JSON" --> API
    REPO --> TBL
    SCAN -- "read + hash" --> ROOTS
    SCAN -- "write" --> THUMB
    FILES -- "audited moves" --> ROOTS
    FILES -- "audited moves" --> QUAR
```

For complete architectural details, data model, design decisions, and tradeoffs, see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Key design principles

- **Backend layers (strict)**: `api/` (thin routers) → `services/` (use-cases, transactions)
  → `repositories/` (only layer that queries DB). Routers hold no business logic;
  components never fetch directly — they call the typed API client.
- **File safety**: All file moves go through `files/`, which resolves paths with
  containment checks (realpath inside approved scan roots or quarantine dir).
  Never overwrites — collisions get numeric suffixes. Every operation audited.
- **Resumable jobs**: Scan and organize state persists in the DB (`scans` and
  `organize_runs` tables). UI polls every ~1 second for progress. Interrupted jobs
  are marked failed on startup; the next scan's move-detection reconciles any partial
  changes.
- **No overwrite policy**: Duplicates in the destination folder are never silently
  overwritten. Organize collisions are suffixed (`_01`, `_02`…).

## Repository layout

```
.
├── backend/                         # FastAPI app
│   ├── app/
│   │   ├── api/                     # FastAPI routers (thin; no logic)
│   │   ├── services/                # Use-case logic, transactions
│   │   ├── repositories/            # Only layer that queries DB
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   ├── schemas/                 # Pydantic I/O schemas
│   │   ├── scanner/                 # Photo discovery, EXIF, hashing, thumbnails
│   │   ├── dedupe/                  # Duplicate grouping, pHash, LSH candidate search
│   │   ├── files/                   # Path safety, quarantine, organize, audit
│   │   ├── jobs/                    # In-process background job runner
│   │   ├── db/                      # SQLAlchemy session, connection pool
│   │   ├── core/                    # Config (pydantic-settings), structured logging
│   │   └── main.py                  # FastAPI app initialization
│   ├── alembic/                     # Database migrations (0001–0012)
│   ├── tests/                       # pytest (166 tests)
│   ├── .env.example                 # Configuration template
│   ├── requirements.txt             # Dependencies
│   └── requirements-dev.txt         # Test/lint deps (pytest, ruff, mypy)
├── frontend/                        # Vue 3 SPA
│   ├── src/
│   │   ├── views/                   # Routed pages (Home, Library, Duplicates, Organize, Scan, Cleanup)
│   │   ├── components/              # Recreated from design prototypes (grid, lightbox, compare, modals, etc.)
│   │   ├── stores/                  # Pinia stores (theme, library, duplicates, scan, organize, quarantine)
│   │   ├── api/                     # Typed API clients (photos, scans, duplicates, files, organize, etc.)
│   │   ├── router/                  # Vue Router config
│   │   ├── assets/                  # Design tokens as CSS custom properties
│   │   ├── utils/                   # Formatting/grouping helpers
│   │   └── main.ts                  # Vue app entry
│   │       # Vitest specs (84 tests) live in __tests__/ dirs beside the code
│   ├── .env.example                 # Configuration template
│   └── package.json                 # npm dependencies (Vue 3, Pinia, Vite, Vitest)
├── design_handoff_photo_organizer/  # READ-ONLY visual design source of truth
│   ├── screens/                     # Interactive HTML prototypes (*.dc.html)
│   ├── screenshots/                 # Design mockups
│   └── README.md                    # Design spec + tokens
├── docs/
│   └── ARCHITECTURE.md              # System design, data model, decisions, tradeoffs
├── scripts/                         # Local helper scripts (e.g. test-DB init)
├── docker-compose.yml               # PostgreSQL 16 with pgvector (Docker-only; frontend/backend native)
├── TASKS.md                         # Phase-by-phase implementation roadmap
├── CLAUDE.md                        # Project rules, commands, conventions
└── README.md                        # This file
```

## Prerequisites

- **macOS** with Docker Desktop
- **Python 3.12+**
- **Node 20+**
- **Git**

## Getting started

### 1. Start the database

```bash
docker compose up -d
```

Creates a PostgreSQL 16 database at `localhost:5435` (via Docker). Verify with:

```bash
docker compose logs db
```

### 2. Backend setup

```bash
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Copy and review configuration
cp .env.example .env

# Run migrations (creates tables, enables pgvector)
alembic upgrade head

# Start the server (http://localhost:8003)
uvicorn app.main:app --port 8003 --reload
```

### 3. Frontend setup (new terminal)

```bash
cd frontend

# Install dependencies
npm install

# Copy configuration
cp .env.example .env

# Start dev server (http://localhost:5173)
npm run dev
```

Open http://localhost:5173 in your browser. You'll see the Home dashboard with
a link to add scan roots (folders to index).

## Testing & quality gates

### Backend

```bash
cd backend

# Run tests (requires docker compose up -d)
pytest

# Lint
ruff check .

# Format check
ruff format --check .

# Type check
mypy app
```

All 166 backend tests use temporary directories and generated images only —
they never touch a real photo library.

### Frontend

```bash
cd frontend

# Run tests
npm run test

# Run lint + type checks
npm run lint && npm run type-check
```

All 111 frontend tests run in vitest (isolated, mocked API calls).

### Both

To verify the full stack locally:

```bash
# Terminal 1: Database
docker compose up -d

# Terminal 2: Backend
cd backend && source .venv/bin/activate
pytest && ruff check . && mypy app && uvicorn app.main:app --port 8003 --reload

# Terminal 3: Frontend
cd frontend && npm run test && npm run lint && npm run type-check && npm run dev

# Terminal 4: Live browser test
# Open http://localhost:5173, add a scan root, start a scan
```

## Environment variables

### Backend

Defined in `backend/app/core/config.py` as Pydantic `Settings` fields. Copy
`backend/.env.example` and adjust:

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | str | `postgresql+psycopg://aperture:aperture@localhost:5435/aperture` | PostgreSQL connection string |
| `LOG_LEVEL` | str | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `THUMBNAIL_CACHE_DIR` | Path | `~/.aperture/thumbnails` | App-managed thumbnail cache (safe to delete) |
| `QUARANTINE_DIR` | Path | `~/.aperture/quarantine` | Where marked-for-deletion files are moved (reversible) |
| `CORS_ORIGIN` | str | `http://localhost:5173` | Frontend origin allowed by CORS |
| `SCAN_WORKERS` | int | `-1` | Scan CPU workers: -1 = (cores - 1), 0 = serial (debug), N = exactly N |
| `SCAN_BATCH_SIZE` | int | `500` | Photos processed and committed per batch during scan |
| `RECOVER_SCANS_ON_STARTUP` | bool | `True` | Mark orphaned scans (by crash/restart) as failed on startup |
| `THUMBNAIL_SIZE` | int | `512` | Longest-edge pixels for grid thumbnails (generated during scan) |
| `PREVIEW_SIZE` | int | `2048` | Longest-edge pixels for lightbox previews (generated on first request) |
| `SIMILAR_HAMMING_THRESHOLD` | int | `6` | Max Hamming distance for "visually similar" (0–7; >7 loses LSH completeness guarantee) |

### Frontend

Defined in Vite config, sourced from `frontend/.env` (`.env.example` provided):

| Variable | Type | Default | Description |
|---|---|---|---|
| `VITE_API_BASE_URL` | str | `http://localhost:8003` | Backend URL for API calls |

No secrets exist in this app. `.env` files are ignored by git on principle.

## How scanning works

Scans walk configured scan-root directories and process each image in a single I/O pass:

1. **Discovery** (`scanner/discovery.py`): Streaming `os.scandir` generator that walks
   directories, skips symlinks (cycle safety via `(dev, ino)` visited set), skips
   hidden entries, yields per-file errors without aborting.

2. **Change detection** (`scanner/processing.py`): For each file, check if `(size_bytes, mtime)`
   matches the DB. If unchanged, skip. If changed or new, process:
   - Read full file bytes (one read per file)
   - Compute SHA-256 (universal hash → content-based move detection)
   - Decode with Pillow/pillow-heif:
     - Extract dimensions, EXIF (capture time, camera make/model, GPS coordinates)
     - Generate 512px thumbnail → thumbnail cache (content-addressed by SHA-256, so
       byte-identical copies share one thumbnail)
     - Compute 64-bit perceptual hash (pHash)
   - Split pHash into 8 single-byte LSH bands (stored in indexed DB columns)
   - Record the photo row with `status=active` or `status=missing` for files gone since
     last scan

3. **Batching**: Insert/update photos in batches of 500–1000 rows per commit. Corrupt
   or undecodable files still get a row (with `last_error` set) so the user can see
   what went wrong.

4. **Move detection** (next scan): If a file's SHA-256 appears at a new path with the
   old path missing, the photo row is moved, not deleted+added. Preserves photo id,
   decisions, and duplicate group membership.

5. **Job state**: The `scans` table holds `status`, progress counters, `current_path`,
   and timestamps. UI polls every ~1 second. Interrupted scans are marked failed on
   startup; the next scan resumes from the file system.

### CPU-bound work

Decode, hash, and pHash run in a `ProcessPoolExecutor` (default: one worker per core
minus one, configurable with `SCAN_WORKERS`). DB writes happen on the async side in
batches. This keeps the event loop responsive and scales thumbnail generation.

## Duplicate detection

### Exact duplicates

A straightforward `GROUP BY sha256 HAVING count(*) > 1`. After each scan, the
`duplicate_groups` table is updated with all SHA-256 groups.

### Near-duplicates (visually similar)

Two photos are "visually similar" if their 64-bit perceptual hashes are within a
Hamming distance threshold (default: 6). Naive O(n²) comparison at 100k+ photos
(~5×10⁹ comparisons) is untenable, so candidate selection uses **LSH banding**:

1. During scan, the 64-bit pHash is split into 8 single-byte bands and stored in
   indexed DB columns (`phash_b0…phash_b7`).

2. By the pigeonhole principle, any two hashes within Hamming distance 7 must agree
   exactly on at least one band.

3. `GET /api/photos/{id}/similar` finds all photos where any band matches, then
   verifies each candidate with `bit_count((phash # :other)::bit(64)) <= :threshold`.

4. After each scan, a post-scan rebuild clusters verified pairs into groups using
   union-find. Identical hashes are collapsed first (burst shots become one group).

**Why not image embeddings?** Perceptual hashing finds resized/recompressed variants
but misses crops and edits. Image embeddings (e.g., CLIP via pgvector) are the
planned upgrade path and are kept architecturally open: the Postgres image ships with
the pgvector extension, and a future migration would add a `photo_embeddings` table
for semantic similarity search without touching the existing pHash logic.

## Organize workflow

Physical organization moves selected folders' photos into a destination folder with
a chosen folder structure, optional rename, and optional skip-duplicates.

### The plan

`files/organize.py::build_plan` is the **only** code that computes destinations.
Both the preview endpoint and the execute job call it, so the dry-run the user
approves is exactly what runs. Planning is pure DB work (no per-file disk access) so
previews stay sub-second at 50k+ photos:

- **Modes**:
  - `keep`: Photos stay in their current folder hierarchy.
  - `date`: `YYYY/MM/` by capture date; undated photos go to `Undated/`.
  - `camera`: One folder per camera model; unknown goes to `Unknown camera/`.

- **Rename** (optional): `YYYY-MM-DD_HHMMSS.ext` (e.g., `2026-07-12_142350.jpg`).
  Same-second collisions get suffixes: `_01`, `_02`… within the batch.

- **Skip duplicates** (toggle): For byte-identical copies (an exact duplicate group),
  only the group's keeper moves — the other copies stay where they are, for the
  Duplicates review workflow to deal with.

### Destination handling

- The user can pick **any** folder as destination (not just existing scan roots).
- If the destination is outside all scan roots, it's **auto-registered as a new root**
  (the preview flags this with `destination_new_root`), so organized photos stay in
  the Library — the user never manually manages roots.
- **Guard rails**:
  - The quarantine folder is refused.
  - A destination that *contains* an existing root is refused (409), to prevent
    double-indexing.

### Execution

Moves run as a background job (similar to scans): stored in `organize_runs` table,
polled by the UI every ~1 second. The executor updates each `photo.path` and
`photo.root_id` transactionally, appends an `op="organize"` audit row under one
batch id, and commits every 200 moves. A crash loses at most one chunk of DB updates.

- **No overwrites**: A destination is occupied if claimed in-batch or held by **any**
  photos row (the path column is UNIQUE; quarantined rows keep their old paths).
  The executor re-checks `dest.exists()` right before each move.
- **Audit**: Every move recorded in `file_operations` with source, destination, size,
  and batch id.
- **Resumability**: Interrupted runs are marked failed on startup; the next scan's
  SHA-256 move-detection retargets any rows that were partially moved.

## Deletion safety model

Nothing is ever deleted automatically. "Delete" is a three-step explicit workflow:

1. **Mark**: User marks photos in the Library (soft flag `photo.marked_for_deletion`).
   Either one at a time via the 🗑 badge on a tile, or in bulk: select photos in the
   grid and use the selection bar's "Mark for deletion".
2. **Quarantine**: `POST /api/quarantine` moves marked files to `QUARANTINE_DIR`
   (reversible, preserves relative path, recorded in audit log).
3. **Restore or Permanent Delete**: From the Cleanup view, user can restore (move back
   to original location, re-indexed by move-detection) or permanently delete (one-time
   action, recorded in audit log).

All operations validate paths (realpath resolution + containment in approved roots or
quarantine dir), are recorded in the `file_operations` audit log, and prevent removing
all members of a duplicate group by default (unless `force=True` behind a strong
confirmation dialog).

## Generated data locations

These are safe to delete and will be rebuilt:

- **Thumbnails**: `THUMBNAIL_CACHE_DIR` (~/.aperture/thumbnails by default)
  - 512px cached images, keyed by content SHA-256 (identical copies share one).
  - Rebuilt on-demand if missing; regenerated during scans.

- **Previews**: Also in `THUMBNAIL_CACHE_DIR`, at 2048px.
  - Generated on first view (lightbox).

- **Quarantine**: `QUARANTINE_DIR` (~/.aperture/quarantine by default)
  - **NOT** a cache — contains real photos marked for deletion.
  - Restore moves them back to their original location.
  - Only permanent-delete removes them from disk.

Neither is committed to git.

## Ports (fixed on this machine)

See [CLAUDE.md](CLAUDE.md) for why these are reserved:

| Service | Port |
|---|---|
| FastAPI backend | **8003** |
| Vite dev server | 5173 |
| PostgreSQL (Docker) | **5435** |
| Native Postgres (if running) | 5432 |
| Other projects | 5433, 5434, 8000, 8001, 8002, 8010 |

## Limitations & roadmap

**Current limitations:**

- **RAW files are not supported** — no decode/thumbnail/pHash. The design mockups show
  RAW badges; support via `rawpy` is listed as a future consideration.
- **HEIC/HEIF support** depends on `pillow-heif` (included in requirements.txt).
- **Perceptual hash similarity** finds resized/recompressed variants, not crops or
  edits. Image embeddings (CLIP family via pgvector) are the upgrade path.
- **No location UI yet** — GPS coordinates are extracted during scan and stored
  (`photos.latitude`, `photos.longitude`); photos indexed before this feature can be
  backfilled via `POST /api/maintenance/backfill-gps`. The map/grouping UI and
  offline reverse geocoding are future work.
- **No tags** — the design includes a Tags card on the Organize view; deferred.
- **Single user, local only, no authentication** — do not expose the backend beyond
  localhost.
- **In-process jobs** — a crashed backend pauses scans/organize runs (they resume from
  DB state). Accepted for a single-user local tool.

**Roadmap** (deferred / future work):

- Image embeddings (CLIP-family) in `photo_embeddings` table + pgvector ANN for
  semantic similarity and "find edited versions".
- RAW support (metadata-only indexing or `rawpy`-based decode).
- Location UI: reverse geocoding, map view, group by location.
- Tags (from the design).
- Dedicated worker process / real queue (Celery/RQ) if in-process jobs become
  limiting.

See [TASKS.md](TASKS.md) for detailed per-phase tracking.

## Skills

| Area | Stack |
|---|---|
| **Frontend** | Vue 3 (Composition API), TypeScript, Vite, Vue Router, Pinia, Vitest (111 tests) |
| **Styling** | Hand-rolled CSS on design tokens (CSS custom properties); no CSS framework |
| **Backend** | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, pytest (166 tests) |
| **Database** | PostgreSQL 16 (pgvector extension pre-installed for future embeddings) |
| **Imaging** | Pillow, pillow-heif (HEIC/HEIF), ImageHash (perceptual hash) |
| **Scanning** | ProcessPoolExecutor for CPU-bound decode/hash work; single-worker thread job runner (DB-persisted state) for coordination |
| **Duplicate detection** | LSH banding (Hamming distance on pHash), SQLAlchemy generated columns, union-find clustering |
| **File safety** | Path resolution + containment validation, batch-audited operations, soft-delete → quarantine → permanent |
| **Infrastructure** | Docker Compose (Postgres only); frontend/backend run natively on macOS |
| **CI/CD** | None (local-only development) |
| **Code quality** | ruff (lint + format), mypy (type check), Vitest (component testing), pytest (integration testing) |

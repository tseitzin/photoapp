# Aperture — Implementation Tasks

Working rules: small focused PRs (300–600 lines), Conventional Commits, tests and
lint pass before a task is checked, docs updated when behavior changes.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design decisions.

## Phase 1 — Discovery & planning ✅ (2026-07-03)

- [x] Inspect project folder; classify design assets (HTML prototypes + spec, not Vue)
- [x] Summarize design, propose architecture, DB model, dedupe strategy, safety model
- [x] Surface near-duplicate candidate-selection decision (LSH banding recommended;
      pgvector path kept open)
- [x] Create README.md, docs/ARCHITECTURE.md, TASKS.md, CLAUDE.md
- [x] **Decision (Tim, 2026-07-03):** LSH banding approved for near-dup candidate
      selection
- [x] **Decision (Tim, 2026-07-03):** RAW skipped entirely in v1

## Phase 2 — Development foundation ✅ (2026-07-03)

- [x] **PR 2.1 — repo + scaffolds**: git init, .gitignore, docker-compose.yml
      (pgvector/pgvector:pg16, host port 5435), create-vue scaffold (Vue 3 + TS +
      Router + Pinia + Vitest + ESLint), backend venv + FastAPI skeleton,
      .env.example files
- [x] **PR 2.2 — backend core**: pydantic-settings config, JSON structured logging,
      SQLAlchemy 2 session setup, Alembic + migration 0001 (enable pgvector ext),
      GET /api/health (200 with database flag even when DB is down), pytest smoke
      tests; verified live on :8003 against Docker PG
- [x] **PR 2.3 — frontend shell**: design tokens as CSS custom properties (light/dark
      from the handoff spec), theme store persisted to localStorage['aperture-theme']
      (system preference as fallback), top bar + nav per design, routed placeholder
      views, typed API client (ApiError with status; 0 = unreachable), health wiring
      with offline banner + retry; CORS verified with real Origin header

## Phase 3 — Photo indexing ✅ (2026-07-03)

- [x] **PR 3.1 — scan roots**: model/migration/repo/service/API; rejects relative,
      nonexistent, duplicate, and nested/containing roots; DB test infra
- [x] **PR 3.2 — discovery walker**: streaming scandir generator, symlinks never
      followed, (dev,ino) cycle guard, hidden entries skipped, per-entry errors
      yielded without aborting
- [x] **PR 3.3 — processing pipeline**: single-pass read → sha256 + decode → EXIF/
      dimensions/camera; corrupt files indexed with last_error; ThreadJobRunner +
      ProcessPoolExecutor (SCAN_WORKERS); batched commits; scans API with progress,
      cancel, paginated errors
- [x] **PR 3.4 — incremental rescan**: skip unchanged (size+mtime), missing
      flagged not purged, moves detected by sha256 (photo id preserved),
      interrupted scans failed on startup; basic photos list/detail API
      (pagination + status filter). Verified live end-to-end incl. move+delete
      rescan with the real process pool.

## Phase 4 — Gallery integration

- [ ] **PR 4.1 — thumbnails**: pHash + thumbnail generation in the pipeline, cache
      dir + stable keys, regenerate on change, serve by photo id (no raw paths) + tests
- [ ] **PR 4.2 — library core**: folder tree API + component, photo grid with
      virtual scrolling, pagination API, selection state
- [ ] **PR 4.3 — filters + lightbox**: file-type/camera/rating filters, sort,
      group-by folder/date/camera (location deferred), metadata panel, lightbox with
      keyboard nav + filmstrip
- [ ] **PR 4.4 — home + scan UI**: Home dashboard with real stats API, Scan screen
      (setup → progress → done) polling real scan state, library empty/loading states
- [ ] Frontend tests: photo loading, filtering, scan progress display

## Phase 5 — Duplicate detection

- [ ] **PR 5.1 — exact duplicates**: group by sha256 into duplicate_groups/members
      after scans, groups API with pagination, stats integration + tests
- [ ] **PR 5.2 — similar photos**: 8-band LSH columns + migration, candidate query,
      bit_count verify, union-find grouping, configurable threshold (default 6),
      clearly labeled "visually similar" + tests
- [ ] **PR 5.3 — review UI**: duplicate groups list view, pair compare view
      (similarity dial, diff table) per the design, decisions API
      (keep/remove/undecided), resolved/freed counters
- [ ] Frontend tests: group review, selection, decision recording

## Phase 6 — Safe file management

- [ ] **PR 6.1 — safety core**: path validation (realpath containment), quarantine +
      restore operations, file_operations audit log, exhaustive tests incl.
      traversal/symlink-escape attempts (BEFORE any UI)
- [ ] **PR 6.2 — removal UI**: confirmation flow with full file details + preview,
      whole-group-removal strong warning, quarantine browser + restore, audit view
- [ ] **PR 6.3 — permanent delete**: explicit quarantine-only purge + tests

## Phase 7 — Deferred / future

- [ ] Organize flow (move/tag/rename + destination picker) — conflicts with
      index-in-place; only after Phase 6 safety layer is proven
- [ ] Tags (non-destructive subset of Organize) — could move earlier if wanted
- [ ] pgvector embeddings for semantic similarity
- [ ] RAW support (rawpy), group-by-location, SSE progress

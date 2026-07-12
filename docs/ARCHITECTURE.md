# Aperture — Architecture

Local-first photo library organizer. Single user, no auth, never exposed beyond
localhost. Originals are read-only to the app except for the explicit, audited
file workflows in `files/` (quarantine and organize).

## System overview

```
┌──────────────────────────┐        ┌─────────────────────────────────────────┐
│  frontend (Vue 3, :5173) │        │  backend (FastAPI, :8003)               │
│                          │  HTTP  │                                         │
│  views ── stores (Pinia) │───────▶│  api/ ──▶ services/ ──▶ repositories/   │
│      └── api client      │        │              │                │         │
└──────────────────────────┘        │              ▼                ▼         │
                                    │  jobs/ ─▶ scanner/, dedupe/  models/    │
                                    │              │              (SQLAlchemy)│
                                    │              ▼                │         │
                                    │           files/ (path safety)│         │
                                    └──────────────┼────────────────┼─────────┘
                                                   │                │
                          ┌────────────────────────┼────┐   ┌───────▼────────┐
                          │ filesystem              │    │   │ PostgreSQL 16 │
                          │  photo roots (read-only)│    │   │ Docker :5435  │
                          │  thumbnail cache (rw)   │    │   │ (pgvector img)│
                          │  quarantine dir  (rw)   │    │   └────────────────┘
                          └─────────────────────────┘
```

## Backend layers

| Layer | Responsibility | Rule |
|---|---|---|
| `api/` | FastAPI routers, request/response wiring | Thin. No business logic, no ORM queries. |
| `schemas/` | Pydantic models for all API I/O | API never returns ORM objects. |
| `services/` | Use-cases: scan orchestration, duplicate review, stats | Owns transactions. |
| `repositories/` | All DB access | Only layer that writes queries. |
| `scanner/` | Directory walking, EXIF, hashing, thumbnails | Pure logic, no HTTP; testable in isolation. |
| `dedupe/` | Exact grouping, pHash, LSH candidate search, connected components | Same. |
| `files/` | Path validation, quarantine/restore operations | The only code allowed to move files. |
| `jobs/` | In-process background job runner | Queue-shaped interface (see Background work). |
| `models/`, `core/` | SQLAlchemy models; config (pydantic-settings) + structured logging | Config never hard-coded. |

## Frontend structure

- `views/` — Home, Library, Duplicates, Organize, Scan, Cleanup; routed via Vue Router.
- `components/` — recreated from the design prototypes (top bar, folder tree, photo
  grid, lightbox, compare panes, dial, toggles, segmented controls, modals).
- `stores/` — Pinia: `theme` (persisted to `localStorage['aperture-theme']`),
  `library`, `duplicates`, `scan`, `quarantine`, `organize` — mirroring the handoff
  doc's state model. The Organize working set is the library store's folder
  checkboxes (`checkedFolders`/`checkedTopLevel`) — one source of truth shared
  across the Library sidebar and the Organize screen.
- `api/` — single typed client module per resource; components never call `fetch`.
- Styling: design tokens as CSS custom properties on the root, swapped for light/dark.
  No CSS framework — the design is hand-rolled and stays that way.

## Data model

```
scan_roots ─┬──▶ photos ◀──┬─ duplicate_group_members ──▶ duplicate_groups
            │      │       └─ duplicate_decisions ───────────────┘
scans ──────┘      ├──▶ file_operations (audit)
   └─▶ scan_errors └──▶ photo_embeddings (future, pgvector)
```

- **scan_roots** — configured library directories. `id, path (unique), enabled, created_at`.
- **photos** — one row per discovered file. Identity: `path` (unique). Fields:
  `root_id, filename, ext, mime, size_bytes, mtime, width, height, captured_at,
  camera_make, camera_model, latitude, longitude, exif JSONB, sha256 (indexed), phash BIGINT,
  phash_b0..phash_b7 SMALLINT (each indexed), status (active|missing|quarantined),
  marked_for_deletion (indexed), thumb_status, last_error, created_at, updated_at`.
  Change detection: `(size_bytes, mtime)` differs → reprocess. Same `sha256` seen at a
  new path with the old path missing → move, not delete+add.
  `marked_for_deletion` is a soft flag set from the Library (no file movement); the
  quarantine work-list (`GET /api/photos/marked`) is the union of flagged photos and
  duplicate `remove` decisions. Quarantining a photo clears the flag.
- **scans** — persisted job state: `status (pending|running|paused|completed|failed|cancelled),
  phase, files_found, files_processed, files_added, files_changed, files_missing,
  error_count, current_path, started_at, finished_at`. Progress UI polls this;
  persistence is what makes scans resumable.
- **scan_errors** — `scan_id, path, error, created_at`. Errors never abort a scan.
- **duplicate_groups** — `kind (exact|similar), key, status (pending|reviewed|dismissed)`.
  Exact groups keyed by sha256; similar groups are connected components over verified
  pHash pairs, `key` = representative photo.
- **duplicate_group_members** — `group_id, photo_id, similarity_pct`.
- **duplicate_decisions** — `group_id, photo_id, decision (keep|remove|undecided),
  decided_at`. This is the "user decisions" tracking — review state, not accounts.
- **organize_runs** — persisted job state for physical organize (Phase 7), polled
  like scans: `status (pending|running|completed|failed), params JSONB (the
  submitted spec), batch_id, total, planned, moved, skipped_duplicates,
  already_organized, undated, failed_count, est_bytes, message, timestamps`.
- **file_operations** — audit log: `photo_id, op (quarantine|restore|delete|organize),
  src_path, dest_path, size_bytes, batch_id, performed_at`. Never auto-pruned
  by the system. `size_bytes` is captured at operation time so lifetime tallies
  (photos deleted, disk space reclaimed = `SUM(size_bytes) WHERE op='delete'`)
  survive after the photo row is gone — the count is exact; byte totals accrue
  only for deletions recorded after `size_bytes` was added (migration 0009).
  The user can explicitly reset the tally (`POST /api/file-operations/reset`),
  which clears rows for removed files (`photo_id IS NULL`) — every delete record
  plus stale quarantine records — while keeping rows for photos that still exist
  (e.g. currently quarantined), so restore is unaffected.

Originals are never stored in Postgres — paths and metadata only.

## Scan pipeline

```
walk roots (os.scandir, no symlinked dirs, realpath visited-set)
  └─▶ per file: stat → unchanged (size+mtime match)? skip
        └─▶ single I/O pass: read bytes
              ├─ SHA-256
              └─ decode (Pillow/pillow-heif)
                   ├─ dimensions + EXIF (captured_at, camera, GPS…)
                   ├─ thumbnail → cache (key: photo id + content hash)
                   └─ pHash (64-bit) → split into 8 LSH bands
        └─▶ batch upsert (500–1000 rows/commit), update scan counters
  └─▶ end of walk: paths not seen → status=missing
```

Decisions worth recording:

- **One read per file, hash everything.** The spec suggested size-first staged
  hashing, but thumbnails/pHash/dimensions already force a full read+decode of every
  image, so SHA-256 over the same bytes is nearly free. Universal hashes also give
  content-based move detection and simpler incremental rescans. Size grouping remains
  only as a query-level pre-filter.
- **CPU-bound work (decode, hash) runs in a `ProcessPoolExecutor`** so the event loop
  stays responsive; DB writes happen on the async side in batches.
- Corrupt/undecodable files still get sha256 + a `photos` row with `last_error` set.

## Duplicate detection

**Exact:** `GROUP BY sha256 HAVING count(*) > 1` materialized into `duplicate_groups`
after each scan.

**Near-duplicate:** 64-bit pHash compared by Hamming distance. Naive O(n²) is
untenable at 100k+ (~5×10⁹ comparisons), so candidate selection uses **LSH banding
in Postgres**: the hash is split into 8 single-byte bands stored in indexed columns.
By pigeonhole, any two hashes within Hamming distance 7 agree exactly on at least one
band, so `WHERE phash_b<i> = :band_i` (8 index lookups per photo) finds every
candidate for the default threshold (6); candidates are verified with
`bit_count((phash # :other)::bit(64)) <= :threshold` (PG14+; `bit_count` takes
`bit`, not `bigint`). The band columns are Postgres generated columns, so the
DB maintains them for free. The post-scan rebuild runs the same banding
in-memory over all active photos (loading 100k (id, sha, phash) rows is ~10 MB);
the SQL path serves per-photo lookup (`GET /api/photos/{id}/similar`). Verified
pairs are clustered into groups via union-find; identical hashes collapse to one
representative first, so burst shots cost one comparison, not O(k²).

Alternatives considered:

- *BK-tree in memory* — exact for any threshold and trivial at this scale, but state
  lives outside Postgres and rebuilds on every restart. Rejected for v1: LSH gives the
  same result set inside the existing store.
- *Image embeddings + pgvector* — the only option that catches crops/edits/semantic
  near-dups. Deliberately kept open, not built: the compose image ships pgvector, and
  embeddings land in a separate `photo_embeddings(photo_id, model, embedding vector)`
  table via a future migration. Nothing in the current schema assumes Hamming-only
  similarity.

Similar groups are always labeled "visually similar", never "duplicate" — only
sha256-equal files are called exact duplicates.

## Background work

v1 is a deliberate minimum: an in-process asyncio job runner inside the FastAPI
process, one active scan at a time, CPU work in a process pool. What makes it
replaceable later: job state lives in the DB (not in memory), services enqueue
through a small `JobRunner` interface, and workers are plain functions taking a job
id — the same shape Celery/RQ/arq expect. Swapping the runner is a wiring change,
not a rewrite. No Redis/Celery until the single-process model actually hurts.

Frontend progress: polling `GET /api/scans/{id}` at ~1s. Chosen over SSE/WebSocket
for v1 simplicity; SSE is a compatible upgrade if polling feels laggy.

## File-operation safety

- All mutating file ops go through `files/`, which resolves the target with
  `Path.resolve(strict=True)` and requires containment in an approved root
  (or the quarantine dir for restores). No API accepts raw filesystem paths for reads
  either — thumbnails/previews are served by photo id.
- Quarantine preserves the source-relative path under `QUARANTINE_DIR` and records a
  `file_operations` row; restore is the inverse. Both are covered by tests before any
  UI exposes them (Phase 6).
- Removing every member of a duplicate group is refused by default; the "Remove
  both" review action allows it only with `force` (behind a strong-confirmation
  dialog in the UI).

## Organize (Phase 7)

Physical organization: moves selected folders' active photos into a destination
structure — `keep` (current folder names), `date` (`YYYY/MM/`, no-capture-date →
`Undated/`), or `camera` (one folder per model). Optional rename to
`YYYY-MM-DD_HHMMSS.ext` (same-second collisions get `_01`, `_02`…) and
skip-duplicates (only the exact-group keeper moves).

- `files/organize.py::build_plan` is the **only** code computing destinations;
  `POST /api/organize/preview` (dry-run) and the execute job both call it, so the
  preview the user approves is what runs. Planning is pure DB work — three indexed
  queries, zero per-file disk access — so previews stay sub-second at 50k+ photos.
- Collisions never overwrite: a destination is occupied if claimed in-batch or held
  by **any** photos row (the path column is UNIQUE; quarantined rows keep their old
  paths). The executor re-checks `dest.exists()` right before each move.
- Execution is a background job (`organize_runs` row + `ThreadJobRunner`, 1s
  polling, serialized with scans). Each move updates `photo.path/filename` (and
  `root_id` for cross-root moves) transactionally and appends an `op="organize"`
  audit row under one batch id; commits every 200 moves. A crash loses at most one
  chunk of DB updates — the next scan's sha256 move-reconciliation retargets the
  rows, and interrupted runs are marked failed on startup.
- Duplicate groups, decisions, and the thumbnail cache are untouched by moves
  (photo-id / content-hash keyed); the folder tree is derived from paths per request.

## Key dependencies

| Dependency | Why |
|---|---|
| Pillow + pillow-heif | Decode JPEG/PNG/GIF/WebP/TIFF + HEIC/HEIF |
| ImageHash | Battle-tested pHash implementation |
| SQLAlchemy 2 + Alembic + psycopg | ORM + migrations |
| pydantic-settings | Typed config from environment |
| pgvector/pgvector:pg16 (image) | Keeps the embeddings upgrade path open at zero cost |

## Tradeoffs

- **Postgres over SQLite** — deliberate stack-consistency choice across this user's
  projects; costs a Docker dependency, buys bit_count/JSONB/pgvector and parity with
  sibling apps.
- **Polling over SSE** — trivial to implement/debug locally; ~1 req/s cost is nothing.
- **In-process jobs** — a crashed backend pauses a scan (it resumes from DB state);
  accepted for a single-user local tool.
- **pHash-only similarity in v1** — misses crops/edits; explicit upgrade path via
  pgvector.
- **Desktop-first** — the 3-pane design collapses acceptably to tablet; phone gets a
  browse-only degradation, not parity. A real phone UI would be a redesign.

## Future considerations

- Image embeddings (CLIP-family) in `photo_embeddings` + pgvector ANN for semantic
  similarity and "find edited versions".
- RAW support via `rawpy` (decode for thumbnails/pHash) or metadata-only indexing.
- Group-by-location UI: coordinates are now extracted during scans
  (`photos.latitude/longitude`; `POST /api/maintenance/backfill-gps` for photos
  indexed earlier) — what remains is offline reverse geocoding + the view.
- Tags (the design's Organize screen includes a Tags card, deferred from v1).
- Dedicated worker process / real queue if in-process jobs become limiting.

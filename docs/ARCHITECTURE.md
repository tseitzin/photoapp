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

- `views/` — Home, Library, Duplicates, Organize, Scan, Quarantine; routed via Vue Router.
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
  camera_make, camera_model, latitude, longitude,
  city, region, country, place_distance_km (nearest known place), exif JSONB, sha256 (indexed), phash BIGINT,
  phash_b0..phash_b7 SMALLINT (each indexed), status (active|missing|quarantined),
  marked_for_deletion (partial index), last_error, created_at, updated_at`.
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

### Indexing strategy (migrations 0013, 0015, 0016)

The Library's list query filters on `status` plus any of folder / extension /
camera / filename, and sorts by capture date, filename or size. Each index
therefore **leads with `status`** (every list query constrains it) and **ends with
`id`** (the tiebreaker every sort already applies), so Postgres can walk the index
in output order instead of sorting:

| Index | Serves |
|---|---|
| `(status, captured_at DESC NULLS LAST, id DESC)` | the default sort |
| `(status, captured_at ASC NULLS LAST, id ASC)` | ascending — a backward scan of the above yields NULLS FIRST, so it cannot serve this |
| `(status, filename, id)` | name ascending, and descending backwards |
| `(status, size_bytes, id)` | size, both directions |
| `path text_pattern_ops` | the folder filter's `LIKE 'dir/%'`; the unique index on `path` uses the database collation and cannot serve a prefix match |
| GIN `pg_trgm` on `filename` | filename search's leading-wildcard `ILIKE` |
| `(status, directory)` | the folder count and folder tree, both index-only |
| `(status, sha256, size_bytes)` | exact-duplicate lookups, and the stats duplicate preview index-only |

`status` has no index of its own — essentially every row is `active`, so alone it
has no selectivity. `marked_for_deletion` is partial (`WHERE marked_for_deletion`)
for the same reason inverted: only a handful of rows qualify.

Two rules that keep this honest:

- **Indexes are declared on the model *and* in the migration.** Tests build the
  schema with `create_all` and production with Alembic, so the two can drift
  silently — and a missing index costs nothing at 4k photos and everything at 50k.
  `tests/test_photo_indexes.py` asserts they agree.
- **List queries defer `photos.exif`.** It averages ~1.3 KB and lives inline in the
  heap, so it dominates the bytes a page read touches, and no list schema exposes
  it. Only `PhotoDetail`, via `get()`, loads it.

### Aggregates read the index, not the table

`GET /api/stats` and `GET /api/folders` used to be four sequential scans of a
27 MB table, two of them deriving `regexp_replace(path, '/[^/]*$', '')` per row —
a function call no index can serve. `photos.directory` is now a stored generated
column, so the derivation happens once at write time and both queries walk
`(status, directory)` without touching the heap. Measured on 100k rows over 2,000
folders: the folder count went 169.7 ms / 16,670 buffers to 6.5 ms / 93, and the
folder tree 88.9 ms / 16,704 to 9.1 ms / 93.

Two details that decide whether any of this pays off:

- **`count(DISTINCT x)` makes the planner sort every row.** Grouping in a subquery
  and counting the groups produces the same answer from an index-only scan. The
  same rewrite, same index, six times quicker.
- **An index-only scan is only index-only when the visibility map is current,**
  and autovacuum's defaults do not suit an imported library: it triggers on
  updates and deletes, so inserting 50k photos leaves the map stale and every
  "index-only" scan falls back to the heap. Measured on the real library, a plain
  `VACUUM` turned `count(*)` from a 1,024-buffer sequential scan (7.07 ms) into an
  8-buffer index-only scan with zero heap fetches (0.41 ms). Migration 0016 lowers
  the vacuum, insert-vacuum and analyze scale factors on `photos` so a large
  import is followed by a vacuum instead of waiting for 20% churn.

`exif` storage was *not* changed. It was a candidate — inline at ~1.3 KB, it made
every sequential scan a third more expensive — but the scans that suffered are
now index-only and never read it, list queries already defer it, and a
`LIMIT`-bounded index scan costs the same with or without it (measured: 98 buffers
either way). Moving it out of line would have added a TOAST fetch to the detail
view in exchange for nothing.

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
- **A reader thread pulls files into the page cache ahead of the pool**
  (`SCAN_PREFETCH`, 0 disables), so a worker's core does not idle waiting on the
  disk. It passes nothing between processes — the payload is the page cache, and
  a pickled buffer would cost more than the stall it removes.

### What actually limits an import

Measured importing 1,556 phone photos (3.3 GB, 41% HEIC) from a USB drive, on an
M3 with 7 workers: **83.8s, 18.6 photos/s, zero errors**. Where that went:

| | |
|---|---|
| SQL, whole import | 140 ms — 0.17%, and inserts batch 1,000 rows into 2 statements |
| reverse geocoding | 17 ms for 1,386 lookups, though it runs in the parent |
| scan orchestration | ~5s — the bare pool over the same files took 79.2s of the 83.8s |
| everything else | decode, hash, pHash, thumbnail |

So the scan pipeline is not the cost; `process_file` is. HEIC costs 213 ms per
photo against JPEG's 64 ms, and decode throughput plateaus at **3.2x** no matter
how many workers are added — an M3 has 4 performance and 4 efficiency cores, and
the efficiency cores contribute little to image decoding. 4 workers reach 3.01x,
7 reach 3.22x; the extra three buy 7% for about 2.3 GB of resident memory.

The drive is the other wall: 116 MB/s sequential, and **115 MB/s with seven
concurrent readers** — 0.99x. Concurrency cannot make it faster, which is why
reading ahead on one thread is the only lever available on the I/O side.

Worth knowing when a count looks wrong: `SUPPORTED_EXTENSIONS` has no video
formats, so `.mov`/`.mp4` are skipped at discovery, and an ExFAT volume carries
an AppleDouble `._` stub beside every file which is skipped as a dotfile. The
import above found 1,556 photos in a folder of 1,579 files for those two reasons.
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

### Cost, and the two rules that bound it

Banding makes the pass *complete* for threshold ≤ 7, but comparisons are still
quadratic **within a band bucket**: with n well-spread hashes over 8 bands × 256
buckets it does on the order of n²/64 distance checks. Measured: 0.25 s at
n=4.5k, 3.3 s at n=18k.

- **Memory must stay linear.** An earlier version memoized every compared pair,
  which peaked at 418 MB by n=18,000 and projected past 3 GB at 50k — enough to
  kill the process. Union-find already makes repeated merges idempotent, so the
  memo was unnecessary; a `find()`-equality check replaces it, is cheaper than the
  lookup it removes, and keeps peak memory in single-digit MB.
- **The rebuild is skipped when a scan changed nothing.** Derived groups are a
  pure function of the active photo rows, so a rescan that added, changed, moved
  and lost nothing cannot change them. Without the guard, the most expensive part
  of a scan ran on every no-op rescan.

### The bounded rebuild

n²/64 is paid over the *whole library*, so importing a few hundred photos into a
large one used to re-derive every group from every photo. `rebuild_groups_for`
bounds the work to a subgraph around what the scan changed; `execute_scan` uses
it and falls back to the full pass once a scan has touched more than 25% of the
active library, where bounding no longer saves anything.

Measured against a synthetic library of uniformly random hashes:

| library | imported | full pass | bounded | |
|---|---|---|---|---|
| 50,000 | 200 | 7.46 s | 0.15 s | 51× |
| 100,000 | 200 | 29.7 s | 0.25 s | 121× |
| 100,000 | 1,000 | 30.3 s | 0.59 s | 51× |
| 100,000 | 5,000 | 32.6 s | 2.01 s | 16× |

The bounded pass tracks *import* size, not library size — which is the point.

Two things make it correct, and one nearly made it useless:

- **The subgraph must be closed.** It holds whole components, not just the new
  photos and their neighbours, or a derivation would split a group that extends
  past its edge. Scope is seeded from the neighbours rather than from the touched
  photos alone: a new photo belongs to no group yet, so the group it is about to
  join is only reachable through the neighbour it joins. Components are maximal
  and adding photos only ever merges them, never splits one, so nothing outside
  the subgraph can be within the threshold of anything inside it.
- **Only in-scope groups may be deleted.** The full pass deletes any group absent
  from its derivation; here that would delete every untouched group in the library.
- **Band equality alone cannot select the neighbours.** It is a candidate filter
  with a ~1/32 false-positive rate per pair. That is fine for one hash, and
  useless in bulk — the band values of 200 seeds cover most of each band's 256
  possible values, so nearly every photo "matches" and the subgraph becomes the
  whole library. The first implementation did exactly this and measured *slower*
  than the full pass. The distance check therefore happens in SQL, in
  `_neighbour_ids`, against the same indexed bands the lightbox uses.

## Place names

`geo/places.py` turns coordinates into the nearest known place, entirely offline:
a k-d tree over ~150k GeoNames cities bundled with `reverse_geocoder`. A web
geocoding API was never a candidate — the coordinates of someone's photos are
exactly what a local-first app must not send anywhere.

Three consequences worth knowing:

- **It names the nearest place, not the place you were in.** How close that is
  depends entirely on the terrain. Measured over a real 4,500-photo library:
  84% of matches land within 5 km (the town itself), 16% fall between 5 and
  25 km, and a handful sit beyond that — the spread is settled suburbs versus
  open country, not lookup error. `Place.distance_km` is therefore part of the
  result and the UI renders "near Gorham, New Hampshire" past 5 km. Beyond
  `PLACE_MAX_KM` (default 100) nothing is recorded at all: naming a city across
  an ocean is worse than admitting we don't know.
- **The tree costs ~100 MB resident**, so it is imported and built lazily on
  first use — a library with no GPS data never pays for it — and only ever in
  the parent process. Building it inside each scan worker would multiply that by
  the worker count, which is why `_place_fields` is applied where scan results
  are persisted rather than inside `process_file`.
- **Place names are stored, not derived per request** (`photos.city/region/
  country/place_distance_km`, migration 0014). They are what a future
  group-by-location would filter on, and the read path stays a plain column
  select. `reverse_geocoder.search` must be called with `mode=1`; the default
  forks a process pool, which must not happen inside a web worker or a job.

Geocoding never fails a scan: any error yields no place and is logged.

## Background work

v1 is a deliberate minimum: an in-process asyncio job runner inside the FastAPI
process, one active scan at a time, CPU work in a process pool. What makes it
replaceable later: job state lives in the DB (not in memory), services enqueue
through a small `JobRunner` interface, and workers are plain functions taking a job
id — the same shape Celery/RQ/arq expect. Swapping the runner is a wiring change,
not a rewrite. No Redis/Celery until the single-process model actually hurts.

Frontend progress: polling `GET /api/scans/{id}` at ~1s. Chosen over SSE/WebSocket
for v1 simplicity; SSE is a compatible upgrade if polling feels laggy.

## Observability

Tracing is off unless `TELEMETRY_ENABLED=1`, and vendor-neutral: the same spans
reach Honeycomb or a local collector by changing `OTEL_EXPORTER_OTLP_ENDPOINT`.
Turn it on per session rather than in `.env`, so the safe default survives.

```
GET /api/stats (server)
├── connect                          (client, first use of a pooled connection)
├── SELECT count(*) … photos         (client, 19ms)
├── SELECT count(distinct(regexp_replace(path …)))   (client, 33ms)
└── … four more
```

**Nothing on a span describes the library.** This is the constraint the whole
design answers to — spans leave the machine, and a photo path is both private
and self-describing. Three mechanisms, each covered by a test rather than a
convention:

- `redact_url_attributes` reduces `url.full`/`http.target` to the path and blanks
  `url.query`, because `?folder=/Users/…/Pictures/2019` is an ordinary request.
- `add_attributes` refuses any custom value that looks like a path, and
  `record_failure` records an exception's *type* only — an `OSError` message
  carries the filename it failed on, and a traceback carries source paths.
- Query spans are safe because every value in this codebase travels as a bind
  parameter: `db.statement` is parameterised SQL (`WHERE path = %(path_1)s`).
  `tests/test_db_telemetry.py` pins this with an allowlist of span attributes, so
  a raw f-string in a repository — or an OTel upgrade that starts attaching a
  connection string — fails a test instead of shipping paths to a third party.

The resource deliberately omits the process and OS detectors, which would attach
the hostname and command line.

**Sampling.** `/health`, `/thumbnail` and `/preview` are excluded from HTTP
tracing because one photo grid requests hundreds of thumbnails. Those requests
still query the database, so `ParentedClientSpans` drops client spans that have
no parent — otherwise each excluded request would emit a *rootless* `SELECT`
span and the exclusion would backfire into more volume than it saved. Server and
internal spans are unaffected, so a background scan still opens its own trace.

Consequence worth knowing: two queries differing only by a bound value share one
`db.statement`, so Honeycomb groups them into a single row. In `/api/stats` the
active-photo count and the missing-photo count look like one query run twice.

**Scan cost.** The scan takes one deliberately coarse span for the whole job,
with per-file totals as `aperture.*` attributes — a span per file would be ~4,500
per scan, re-encoding what the counters already hold. Measured: a no-change
rescan of 4,491 photos across 4 roots cost **17 spans** (1 scan, 8 SELECT,
6 connect, 2 UPDATE) and 1.84s. Volume tracks batches and roots, not library size.

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
- The user may pick **any** destination folder. If it lies outside the indexed
  scan roots, starting the run registers it as a new root automatically (the
  preview flags this with `destination_new_root`), so organized photos stay in
  the Library — the user never manages roots by hand. Guard rails: the
  quarantine folder is refused, and a destination that *contains* an existing
  root is refused (409) because it would double-index.
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

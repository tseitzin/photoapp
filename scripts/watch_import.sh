#!/usr/bin/env bash
# Sample an in-progress scan and everything around it, one JSON line per tick.
#
# Answers "is the import running as fast as it can" by recording the three
# places a photo import can be bottlenecked at the same instant:
#   - throughput: files processed per second, from the scan row
#   - the pool:   CPU% and RSS per worker, so a saturated pool is visible as
#                 ~100% each, and a parent-bound stall as one busy process
#   - Postgres:   commits, rows inserted, and what backends are waiting on
#
# Usage:  scripts/watch_import.sh [interval_seconds] [output.jsonl]
set -uo pipefail

INTERVAL="${1:-5}"
OUT="${2:-/tmp/aperture-import.jsonl}"
API="http://localhost:8003/api"
CONTAINER="aperture-db"

prev_commits=0
prev_inserts=0
prev_files=0
prev_time=$(python3 -c 'import time; print(time.time())')

echo "sampling every ${INTERVAL}s -> ${OUT}  (Ctrl-C to stop)" >&2

while true; do
  now=$(python3 -c 'import time; print(time.time())')

  scan=$(curl -s -m 5 "${API}/scans?limit=1" 2>/dev/null)
  db=$(docker exec "$CONTAINER" psql -U aperture -d aperture -At -F'|' -c \
    "SELECT (SELECT xact_commit FROM pg_stat_database WHERE datname='aperture'),
            (SELECT coalesce(sum(n_tup_ins),0) FROM pg_stat_user_tables),
            (SELECT count(*) FROM pg_stat_activity WHERE datname='aperture' AND state='active'),
            (SELECT coalesce(string_agg(DISTINCT wait_event, ','),'') FROM pg_stat_activity
               WHERE datname='aperture' AND state='active' AND wait_event IS NOT NULL),
            (SELECT pg_size_pretty(pg_total_relation_size('photos')))" 2>/dev/null)

  # RSS in KB, CPU% per uvicorn/pool process.
  procs=$(ps -eo pid,pcpu,rss,command 2>/dev/null | grep -E "uvicorn|multiprocessing" | grep -v grep \
          | awk '{cpu+=$2; rss+=$3; n+=1} END {printf "%.1f|%d|%d", cpu, rss, n}')

  python3 - "$now" "$prev_time" "$scan" "$db" "$procs" "$prev_commits" "$prev_inserts" "$prev_files" <<'PY' >> "$OUT"
import json, sys
now, prev_time = float(sys.argv[1]), float(sys.argv[2])
scan_raw, db_raw, procs_raw = sys.argv[3], sys.argv[4], sys.argv[5]
prev_commits, prev_inserts, prev_files = int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8])
dt = max(now - prev_time, 1e-6)

try:
    scan = (json.loads(scan_raw) or [{}])[0]
except Exception:
    scan = {}
db = db_raw.split("|") if db_raw else []
procs = procs_raw.split("|") if procs_raw else []

def num(seq, i, default=0):
    try:
        return int(seq[i])
    except Exception:
        return default

files = int(scan.get("files_processed") or 0)
commits, inserts = num(db, 0), num(db, 1)
row = {
    "t": round(now, 1),
    "scan_id": scan.get("id"),
    "status": scan.get("status"),
    "files_processed": files,
    "files_added": scan.get("files_added"),
    "files_per_sec": round((files - prev_files) / dt, 1) if prev_files else None,
    "errors": scan.get("error_count"),
    "cpu_pct_total": float(procs[0]) if procs else None,
    "rss_mb": round(num(procs, 1) / 1024) if len(procs) > 1 else None,
    "procs": num(procs, 2),
    "pg_commits_per_sec": round((commits - prev_commits) / dt, 1) if prev_commits else None,
    "pg_rows_ins_per_sec": round((inserts - prev_inserts) / dt, 1) if prev_inserts else None,
    "pg_active": num(db, 2),
    "pg_waits": db[3] if len(db) > 3 else "",
    "photos_size": db[4] if len(db) > 4 else "",
}
print(json.dumps(row), flush=True)
# Hand the running totals back to the shell.
with open("/tmp/aperture-watch-state", "w") as fh:
    fh.write(f"{commits} {inserts} {files}")
PY

  if [ -f /tmp/aperture-watch-state ]; then
    read -r prev_commits prev_inserts prev_files < /tmp/aperture-watch-state
  fi
  prev_time=$now
  sleep "$INTERVAL"
done

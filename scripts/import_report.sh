#!/usr/bin/env bash
# Capture the database state that an import changes, so before and after can be
# diffed rather than remembered.
#
#   scripts/import_report.sh baseline   # before the import (resets query stats)
#   scripts/import_report.sh after      # after it finishes
#
# Reads pg_stat_statements for per-query totals, which is the only way to say
# *which* statement dominated rather than just that Postgres was busy.
set -uo pipefail

MODE="${1:-after}"
CONTAINER="aperture-db"
psql() { docker exec -i "$CONTAINER" psql -U aperture -d aperture "$@"; }

echo "===== ${MODE}  ($(date '+%Y-%m-%d %H:%M:%S')) ====="

psql -q <<'SQL'
\echo '--- table sizes ---'
SELECT relname AS table, n_live_tup AS rows,
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       pg_size_pretty(pg_indexes_size(relid)) AS indexes
FROM pg_stat_user_tables WHERE n_live_tup > 0 ORDER BY n_live_tup DESC LIMIT 8;

\echo '--- photos: vacuum + bloat state ---'
SELECT n_live_tup AS live, n_dead_tup AS dead,
       last_vacuum, last_autovacuum, last_analyze, last_autoanalyze
FROM pg_stat_user_tables WHERE relname = 'photos';

\echo '--- index usage on photos (scans since last reset) ---'
SELECT indexrelname AS index, idx_scan AS scans,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes WHERE relname = 'photos' ORDER BY idx_scan DESC LIMIT 12;
SQL

if [ "$MODE" = "baseline" ]; then
  psql -qtc "SELECT pg_stat_statements_reset();" > /dev/null
  echo '--- pg_stat_statements reset; the import starts from zero ---'
else
  psql -q <<'SQL'
\echo '--- slowest statements by total time ---'
SELECT calls,
       round(total_exec_time)::text || ' ms' AS total,
       round(mean_exec_time::numeric, 2)::text || ' ms' AS mean,
       round(max_exec_time::numeric, 1)::text || ' ms' AS max,
       rows,
       left(regexp_replace(query, '\s+', ' ', 'g'), 90) AS query
FROM pg_stat_statements
WHERE query NOT LIKE '%pg_stat_%'
ORDER BY total_exec_time DESC LIMIT 12;

\echo '--- most-called statements ---'
SELECT calls, round(total_exec_time)::text || ' ms' AS total,
       left(regexp_replace(query, '\s+', ' ', 'g'), 90) AS query
FROM pg_stat_statements
WHERE query NOT LIKE '%pg_stat_%'
ORDER BY calls DESC LIMIT 8;
SQL
fi

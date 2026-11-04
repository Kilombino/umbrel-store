#!/bin/sh
# The database side of the app page's backups (Backup → Export / Import), in the PostgreSQL
# image, which has pg_dump and psql (the Roblosats image has neither). The page asks through
# files in $W, its own directory: dump.req → dump.sql; restore.req (with restore.sql) → the
# database replaced by it, in one transaction. Each ends in <op>.done or <op>.err (the error).
W="${DB_TOOL_DIR:-/work/backup}"
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=roblosats PGDATABASE=roblosats PGPASSWORD="$POSTGRES_PASSWORD"
umask 077
mkdir -p "$W"
while :; do
  if [ -f "$W/dump.req" ]; then
    rm -f "$W/dump.req" "$W/dump.done" "$W/dump.err" "$W/dump.sql"
    if pg_dump --no-owner --no-privileges -f "$W/dump.sql.tmp" 2>"$W/dump.log"; then
      mv -f "$W/dump.sql.tmp" "$W/dump.sql" && touch "$W/dump.done"
    else
      rm -f "$W/dump.sql.tmp"; mv -f "$W/dump.log" "$W/dump.err"
    fi
    rm -f "$W/dump.log"
  fi
  if [ -f "$W/restore.req" ]; then
    rm -f "$W/restore.req" "$W/restore.done" "$W/restore.err"
    # Everything else connected (the server's processes) is dropped first; they reconnect
    # and wait on the transaction's locks until it is done.
    if { echo "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid();"
         echo "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
         cat "$W/restore.sql"; } | psql -X -q -v ON_ERROR_STOP=1 --single-transaction -o /dev/null 2>"$W/restore.log"; then
      touch "$W/restore.done"
    else
      mv -f "$W/restore.log" "$W/restore.err"
    fi
    rm -f "$W/restore.log" "$W/restore.sql"
  fi
  sleep 1
done

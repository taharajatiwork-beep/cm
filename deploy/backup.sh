#!/bin/sh
set -eu
dir="${BACKUP_DIR:-backups}"
mkdir -p "$dir"
stamp=$(date +%Y%m%d)
pg_dump --format=custom --file "${dir}/cm-${stamp}.dump" "${DATABASE_URL:-postgresql://cm:cm@localhost:5432/cm}"
find "$dir" -name 'cm-*.dump' -mtime +30 -delete
echo "wrote ${dir}/cm-${stamp}.dump"

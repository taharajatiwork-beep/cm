# Backup and restore

Production uses PostgreSQL. Run the daily dump from a host that can reach the database. Keep 30 days. Archive WAL if the server has `archive_mode=on`.

## Daily dump

```bash
./deploy/backup.sh
```

The script writes `backups/cm-YYYYMMDD.dump` and deletes files older than 30 days.

## Restore drill

Once a month, restore the newest dump into an empty database and run `GET /health/ready`.

```bash
createdb cm_restore
pg_restore -d cm_restore backups/cm-YYYYMMDD.dump
```

Do not restore over the live database.

## WAL

WAL archiving is not turned on by this repository. A sample for a host that will archive WAL itself:

```
archive_mode = on
archive_command = 'test ! -f /var/lib/postgresql/wal_archive/%f && cp %p /var/lib/postgresql/wal_archive/%f'
wal_level = replica
```

Apply that only in the server's `postgresql.conf` after the archive directory exists. The daily `pg_dump` above does not enable it.

## Scheduled dump

`docker-compose.prod.yml` runs `deploy/backup.sh` once a day in the `backup` service and keeps the files in the `cmbackups` volume. On a host without Compose, add a cron line:

```
15 2 * * * cd /opt/cm && DATABASE_URL=postgresql://cm:cm@127.0.0.1:5432/cm ./deploy/backup.sh
```

## Monthly restore test

1. Copy the newest `cm-YYYYMMDD.dump` out of the backup volume.
2. `createdb cm_restore` on a database that is not production.
3. `pg_restore -d cm_restore backups/cm-YYYYMMDD.dump`
4. Point a temporary API at `cm_restore` and open `GET /health/ready`.
5. Drop `cm_restore` after the check. Do not restore over the live database.

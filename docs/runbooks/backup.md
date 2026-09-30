# Backup and restore

Production uses PostgreSQL. The `backup` service runs a daily dump and keeps 30 days.

## Dumps are encrypted and self-verified

`deploy/backup.sh` does not write a plain dump. It:

1. writes `cm-YYYYMMDD-HHMMSS.dump` (plain, briefly, inside the backup volume),
2. encrypts it with **symmetric GPG / AES-256** using `BACKUP_PASSPHRASE`,
3. decrypts it again and runs `pg_restore --list` on the result to prove the
   archive is readable,
4. deletes the plain file, and only then reports success.

If any step fails, every file from that run is removed and the script exits
non-zero. A corrupt or truncated dump therefore cannot sit unnoticed for a month.

Both `DATABASE_URL` and `BACKUP_PASSPHRASE` are required. With no passphrase the
script refuses to run rather than silently storing unencrypted customer data.

```bash
DATABASE_URL=postgresql://… BACKUP_PASSPHRASE=… ./deploy/backup.sh
# → wrote backups/cm-20260929-021500.dump.gpg (verified)
```

**Losing `BACKUP_PASSPHRASE` means losing every backup.** Store it in a password
manager, not only in `.env` on the server.

## Decrypt a dump by hand

```bash
gpg --batch --pinentry-mode loopback --passphrase "$BACKUP_PASSPHRASE" \
    --decrypt backups/cm-YYYYMMDD-HHMMSS.dump.gpg > /tmp/cm.dump
```

## Restore drill

Once a month, restore the newest dump into an empty database and run
`GET /health/ready` against it. The script's own check only proves the archive
is *readable*; this drill proves the data is *usable*.

```bash
gpg --batch --pinentry-mode loopback --passphrase "$BACKUP_PASSPHRASE" \
    --decrypt backups/cm-YYYYMMDD-HHMMSS.dump.gpg > /tmp/cm_restore.dump
createdb cm_restore
pg_restore -d cm_restore /tmp/cm_restore.dump
shred -u /tmp/cm_restore.dump      # the plaintext holds customer data
```

Do not restore over the live database. Drop `cm_restore` after the check.

## WAL

WAL archiving is not turned on by this repository. A sample for a host that will archive WAL itself:

```
archive_mode = on
archive_command = 'test ! -f /var/lib/postgresql/wal_archive/%f && cp %p /var/lib/postgresql/wal_archive/%f'
wal_level = replica
```

Apply that only in the server's `postgresql.conf` after the archive directory exists. The daily `pg_dump` above does not enable it.

Note that a daily dump is at best 24 hours of data loss. If the business cannot
tolerate that, turn on WAL archiving and run `pg_basebackup` more often.

## Scheduled dump

`docker-compose.prod.yml` runs `deploy/backup.sh` once a day in the `backup`
service and keeps the files in the `cmbackups` volume. On a host without Compose,
add a cron line that reads the passphrase from the environment, not from the
command line (a passphrase in `crontab` is world-readable in `/var/spool/cron`):

```
15 2 * * * cd /opt/cm && . ./.env && ./deploy/backup.sh
```

Set `BACKUP_RETENTION_DAYS` to change the 30-day default.

## Monthly restore test

1. Copy the newest `cm-*.dump.gpg` out of the backup volume.
2. `createdb cm_restore` on a database that is not production.
3. Decrypt (above) and `pg_restore -d cm_restore …`.
4. Point a temporary API at `cm_restore` and open `GET /health/ready`.
5. `dropdb cm_restore` and securely delete the plaintext dump.

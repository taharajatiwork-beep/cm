# Deploy CM on an internal server

This is the path that `docker-compose.prod.yml` expects. Do not start it with the development `.env` secrets left as placeholders. `APP_ENV=production` refuses a placeholder `SECRET_KEY`, a SQLite URL, and debug mode.

## 1. Prepare the host

- Docker Engine and the Compose plugin.
- A DNS name that staff browsers trust, and a TLS certificate in `deploy/certs` (`fullchain.pem` and `privkey.pem`). nginx in `deploy/nginx.conf` reads those paths.
- Generate the secrets instead of copying the example — it fills `DATABASE_URL` correctly, which is the error operators make most often:

  ```bash
  sh deploy/make-secrets.sh
  # set CORS_ORIGINS to your real https host, then:
  cp .env.prod.local .env
  ```

  Leave `FILE_BACKEND=local` until MinIO is reachable, then set `FILE_BACKEND=s3`, `S3_ENDPOINT=http://minio:9000`, `S3_BUCKET=cm`, and the MinIO keys from the generated file.

## 2. Start

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

Services: Postgres (pgvector), Redis, MinIO, one API, one worker (`python -m app.worker`), the web image, nginx on 443, Prometheus, Grafana on 127.0.0.1:3000, Loki, and a daily `backup` service.

A second API is the same image started again and added to nginx. Compose does not start a replica by itself.

## 3. Check

- `GET /health/ready` through nginx returns 200.
- `GET /metrics` is scraped by Prometheus (`deploy/prometheus.yml` targets `api:8000`).
- Grafana dashboard **CM** shows `cm_http_requests_total`.
- Sign in on the web UI and open Home.

## 4. Files and backups

Uploads stay on the API disk when `FILE_BACKEND=local`. With `s3` they go to the MinIO bucket. The backup service runs `deploy/backup.sh` every 24 hours. The restore drill is in [backup.md](backup.md).

## 5. If this machine has no Docker

Install Docker on the internal server and run the commands above there. A laptop without the Docker CLI cannot bring this compose file up.

# Deployment Guide

Multi-environment deploy script for general-chatbot-api. Each environment (dev/stag/prod) has its own folder containing `docker-compose.yml`, `.env`, and `VERSION`.

## Folder structure

```
deploy/
├── deploy.sh           # shared script
├── README.md
└── dev/
    ├── docker-compose.yml
    ├── VERSION         # semver, e.g. 1.0.0
    ├── BRANCH          # git branch to pull, e.g. develop
    ├── .env.example    # template (committed)
    └── .env            # real config (gitignored, created on server)
```

Each environment pulls from its own branch (defined in `BRANCH` file):

| Env | Typical branch |
|---|---|
| dev | `develop` |
| stag | `staging` |
| prod | `main` |

## First-time setup on server

```bash
# 1. Clone the repo
git clone -b develop <repo-url>
cd general-chatbot-api

# 2. Create the env file from the template
cp deploy/dev/.env.example deploy/dev/.env
nano deploy/dev/.env    # fill SECRET_KEY, DATABASE_URI, STORAGE_PUBLIC_URL, OPENAI_API_KEY...

# 3. Deploy
./deploy/deploy.sh dev
```

## Common commands

| Command | Description |
|---|---|
| `./deploy/deploy.sh dev` | Build and deploy using version from `deploy/dev/VERSION` |
| `./deploy/deploy.sh dev -v 1.2.3` | Build and deploy with explicit version (overrides VERSION file) |
| `./deploy/deploy.sh dev --no-cache` | Build with no Docker layer cache (forces fresh rebuild from source) |
| `./deploy/deploy.sh dev -v 1.2.3 --no-cache` | Explicit version + no-cache rebuild |
| `./deploy/deploy.sh dev down` | Stop & remove containers (named volumes preserved) |
| `./deploy/deploy.sh dev down -v` | Stop, remove containers **AND named volumes** (destructive — postgres/redis/minio data lost) |
| `./deploy/deploy.sh dev rollback` | Roll back to the previous image (`:previous` tag) |
| `./deploy/deploy.sh dev use 1.0.0` | Switch to an existing local image tag (no rebuild) |
| `./deploy/deploy.sh dev list` | List local image tags for this environment |

Replace `dev` with `stag` or `prod` for other environments.

### Why use `down` from the script

The compose project name is locked via `name:` in each env's `docker-compose.yml`,
so `cd deploy/dev && docker-compose down` works as well — both target the same
project (`chatbot-api-dev`). Use the script's `down` for consistency and to enable
the `down -v` shortcut.

### When to use `--no-cache`

Default builds reuse Docker layer cache for speed. Pass `--no-cache` when:

- A code change isn't reflected after a normal deploy.
- Pinned dependency versions changed but the lock layer was cached.
- You suspect a corrupted cached layer.

Every build also passes `--pull` automatically so base images stay fresh, and
`up -d --force-recreate` ensures the container restarts even if the `:latest`
tag string was unchanged.

## Releasing a new version

```bash
# On your local machine
echo "1.0.1" > deploy/dev/VERSION
git commit -am "release: 1.0.1"
git push

# On the server
./deploy/deploy.sh dev
```

The script will:
1. Pull the latest code from the branch defined in `deploy/dev/BRANCH`
2. Tag the current `:latest` as `:previous` (for rollback)
3. Build a new image tagged `chatbot-api-dev:1.0.1` and `chatbot-api-dev:1.0.1-<git_hash>`
4. Re-tag it as `:latest`
5. Restart containers with the new image

## Rollback

```bash
# Quick rollback to the immediately previous image
./deploy/deploy.sh dev rollback

# Or roll back to a specific past version
./deploy/deploy.sh dev list           # see what's available
./deploy/deploy.sh dev use 1.0.0
```

## Adding a new environment (e.g. stag)

```bash
mkdir deploy/stag
cp deploy/dev/docker-compose.yml deploy/stag/
cp deploy/dev/.env.example deploy/stag/
echo "1.0.0" > deploy/stag/VERSION
echo "staging" > deploy/stag/BRANCH

# Edit deploy/stag/docker-compose.yml:
#   - container_name: chatbot-api-stag, chatbot-redis-stag
#   - ports: change 8006/6399 to free host ports
#   - image default: chatbot-api-stag
#   - volume names: chatbot_static_stag, chatbot_redis_data_stag

# On the server: create .env from template, then deploy
cp deploy/stag/.env.example deploy/stag/.env
nano deploy/stag/.env
./deploy/deploy.sh stag
```

## Useful checks

```bash
# Container status
sudo docker-compose -f deploy/dev/docker-compose.yml -p chatbot-api-dev ps

# Live logs
sudo docker-compose -f deploy/dev/docker-compose.yml -p chatbot-api-dev logs -f chatbot-api

# Local images for this env
sudo docker images chatbot-api-dev

# Test endpoints (replace host/port per env)
curl http://localhost:8006/docs
curl http://localhost:8006/api/v1/auth/login -X POST \
  -H 'Content-Type: application/json' \
  -d '{"account_name":"admin","password":"123456"}'
```

## Services in the compose file

| Service | Container | Host port | Notes |
|---|---|---|---|
| `chatbot-api` | `chatbot-api-dev` | `8006 → 8000` | FastAPI app |
| `db` | `chatbot-db-dev` | `5442 → 5432` | PostgreSQL 14 — **no volume, ephemeral** |
| `redis` | `chatbot-redis-dev` | `6399 → 6379` | Redis (Celery / cache) |
| `mqtt-broker` | `chatbot-mqtt-dev` | `1893 → 1883`, `9011 → 9001` | Eclipse Mosquitto |

Host ports are shifted so they don't clash with `general-chatbot-files` or any host-level DB/redis/mqtt running on the same server.

**⚠️ Postgres is intentionally volumeless in this compose file.** Data
disappears when the container is recreated. Do NOT use this setup as-is
for anything you care about. For production, add a named volume or an
external bind mount.

## Shared network with `general-chatbot-files`

Both services share a single docker network named `chatbot-shared` so
the media service can reach this project's postgres by container name
(`chatbot-db-dev`) without going through the host.

Create the network ONCE on the server, before the first deploy of
either project:

```bash
sudo docker network create chatbot-shared
```

Both compose files reference it as an **external** network; if the
network doesn't exist, `docker-compose up` will fail with
`network chatbot-shared declared as external, but could not be found`.

From inside the network:

- `chatbot-api` → `db:5432` (same compose project)
- `media-service` → `chatbot-db-dev:5432` (cross-project via shared net)

`media-service-dev`'s `.env` must have:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@chatbot-db-dev:5432/api_proxy
```

## Deploy order on the server (first time)

Postgres lives in this project, so deploy `general-chatbot-api` **first**,
then `general-chatbot-files`:

```bash
# 0. One-time: create the shared network
sudo docker network create chatbot-shared

# 1. Deploy chatbot-api-dev (brings up chatbot-db-dev on chatbot-shared)
cd general-chatbot-api
git pull origin develop
cp deploy/dev/.env.example deploy/dev/.env
nano deploy/dev/.env   # fill SECRET_KEY, OPENAI_API_KEY, STORAGE_PUBLIC_URL
./deploy/deploy.sh dev

# 2. (If schemas are missing) bootstrap tables + seed data
sudo docker exec -it chatbot-api-dev python seed_data.py

# 3. Deploy media-service-dev (joins chatbot-shared, connects to chatbot-db-dev)
cd ../general-chatbot-files
git pull origin develop
cp deploy/dev/.env.example deploy/dev/.env
nano deploy/dev/.env   # fill JWT_SECRET_KEY (must match chatbot-api SECRET_KEY)
./deploy/deploy.sh dev
```

## Verifying cross-service DB connectivity

After both are up:

```bash
# 1. Check both containers are on chatbot-shared
sudo docker network inspect chatbot-shared \
  --format '{{range .Containers}}{{.Name}}\n{{end}}'
# expect: chatbot-api-dev, chatbot-db-dev, media-service-dev

# 2. From inside media-service, ping the chatbot-api db
sudo docker exec -it media-service-dev sh -c \
  "python -c 'import asyncio,asyncpg; asyncio.run(asyncpg.connect(\"postgresql://postgres:postgres@chatbot-db-dev:5432/api_proxy\").fetchval(\"SELECT 1\"))'"
# expect: no error

# 3. End-to-end: login on chatbot-api, then call a files endpoint with that token
curl -X POST http://<SERVER_IP>:8006/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"account_name":"admin","password":"123456"}'
# copy the access_token

curl -X POST http://<SERVER_IP>:8001/media/api/v1/files/upload \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@test.pdf" -F "file_type=private"
```

## Notes

- Requires `docker-compose` v1 (`sudo apt-get install docker-compose`) — the script uses `sudo -E docker-compose`. If you prefer v2 (`docker compose`), update the `COMPOSE` variable in `deploy.sh`.
- The compose file mounts the repo root into `/app` so code changes are picked up on restart. For immutable deploys, remove the `volumes: [../..:/app]` line from `docker-compose.yml`.
- MinIO object storage is **not** included here — it is provided by `general-chatbot-files` on the same server. This service only needs `STORAGE_PUBLIC_URL` and `STORAGE_BUCKET_NAME` in `.env` to build file URLs.
- `SECRET_KEY` (api) must match `JWT_SECRET_KEY` in `general-chatbot-files/.env` so tokens issued by the API validate on the files service.
- `ADMIN_ROLE_ID` must also match across both services.
- Inside the compose network, services reach each other by service name: `db:5432`, `redis:6379`, `mqtt-broker:1883`. Use host port (`5442`, `6399`, etc.) only from the host or from third-party tools.

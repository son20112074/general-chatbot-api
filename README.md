# General Chatbot API (TMS API Service)

## Overview

A Task Management System API built with **FastAPI** following **Clean Architecture** principles. Supports task management, users, roles, KPI tracking, file upload/parsing, chat, and dashboards.

## Tech Stack

- **Language**: Python 3.12
- **Framework**: FastAPI + Uvicorn
- **Database**: PostgreSQL 14 (async via `asyncpg`)
- **ORM**: SQLAlchemy (async) + Alembic (migrations)
- **Cache/Queue**: Redis, MQTT (Eclipse Mosquitto)
- **File Parsing**: Custom parser module (PDF, Word, Excel, Image OCR, Media, Website)
- **Auth**: JWT (HS256)
- **Containerization**: Docker + Docker Compose

## Project Structure

```
general-chatbot-api/
├── server.py                  # Production entry point (workers=1, reload=False)
├── server_dev.py              # Development entry point (reload=True)
├── file_processing_job.py     # Background job for processing unparsed files
├── alembic.ini                # Alembic config for DB migrations
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Docker image (python:3.12.10)
├── docker-compose.yml         # Compose: api + postgres + redis + mqtt
├── run.sh                     # Script to run Docker container
├── .env.example               # Environment variables template
├── .env.docker                # Env for Docker (uses host.docker.internal)
│
├── app/                       # Main application (Clean Architecture)
│   ├── __init__.py
│   ├── core/                  # Core/Infrastructure configs
│   │   ├── config.py          # Settings (pydantic-settings, reads from .env)
│   │   ├── database.py        # SQLAlchemy async engine + session
│   │   ├── init_db.py         # Script to create tables from models
│   │   ├── logger.py          # Logging setup
│   │   ├── exceptions.py      # Custom exceptions
│   │   ├── query.py           # Query builder utilities
│   │   └── file_service.py    # Core file service
│   │
│   ├── domain/                # Domain layer
│   │   ├── models/            # SQLAlchemy ORM models
│   │   │   ├── user.py        # User model
│   │   │   ├── role.py        # Role model
│   │   │   ├── task.py        # Task model
│   │   │   ├── task_work.py   # TaskWork model
│   │   │   ├── file.py        # File model
│   │   │   ├── kpi.py         # EmployeeKPI model
│   │   │   ├── project.py     # Project model
│   │   │   ├── session.py     # Session model
│   │   │   ├── chat_message.py    # ChatMessage model
│   │   │   ├── chat_history.py    # ChatHistory model
│   │   │   └── personal_task_status.py
│   │   │
│   │   ├── schemas/           # Pydantic schemas (request/response)
│   │   │   ├── kpi.py
│   │   │   ├── task.py
│   │   │   ├── task_work.py
│   │   │   └── migration.py
│   │   │
│   │   ├── services/          # Business logic services
│   │   │   ├── auth_service.py
│   │   │   ├── user_service.py
│   │   │   ├── role_service.py
│   │   │   ├── task_service.py
│   │   │   ├── task_work_service.py
│   │   │   ├── file_service.py
│   │   │   ├── kpi_service.py
│   │   │   ├── migration_service.py
│   │   │   ├── export_task_service.py
│   │   │   ├── export_work_service.py
│   │   │   ├── export_issues_service.py
│   │   │   └── export_employee_performance_service.py
│   │   │
│   │   ├── interfaces/        # Abstract repository interfaces
│   │   │   ├── repositories.py
│   │   │   ├── db_repository.py
│   │   │   └── home_repository.py
│   │   │
│   │   └── entities/          # Base entities
│   │       └── base.py
│   │
│   ├── infrastructure/        # Infrastructure layer
│   │   ├── repositories/      # Concrete repository implementations
│   │   │   ├── raw_repository.py
│   │   │   ├── home_repository.py
│   │   │   └── cache_repository.py
│   │   ├── adapters/
│   │   │   └── websocket_adapter.py
│   │   └── services/
│   │       └── auth_service.py
│   │
│   ├── presentation/          # Presentation layer (API)
│   │   ├── api/v1/
│   │   │   ├── router.py      # Main router - registers all endpoints
│   │   │   ├── deps.py        # Dependencies (auth, db session)
│   │   │   ├── dependencies.py
│   │   │   ├── endpoints/internal/   # API endpoints
│   │   │   │   ├── auth.py           # POST /api/v1/login, /register
│   │   │   │   ├── users.py          # /api/v1/users/*
│   │   │   │   ├── roles.py          # /api/v1/roles/*
│   │   │   │   ├── tasks.py          # /api/v1/tasks/*
│   │   │   │   ├── task_works.py     # /api/v1/task-works/*
│   │   │   │   ├── files.py          # /api/v1/files/*
│   │   │   │   ├── kpis.py           # /api/v1/kpis/*
│   │   │   │   ├── dashboard.py      # /api/v1/dashboard/*
│   │   │   │   ├── migration.py      # /api/v1/migration/*
│   │   │   │   ├── chat.py           # /api/v1/chat/*
│   │   │   │   ├── home.py           # /api/v1/home/*
│   │   │   │   └── common.py         # /api/v1/common/*
│   │   │   ├── schemas/      # API-level schemas
│   │   │   └── routers/
│   │   └── middlewares/
│   │       ├── auth.py        # Auth middleware
│   │       └── logging.py     # Request logging middleware
│   │
│   └── utils/                 # Utility functions
│       ├── helpers.py
│       ├── table_lookup.py
│       └── tree_builder.py
│
├── parser/                    # File parsing module
│   ├── file_parser.py         # Main parser dispatcher
│   ├── config.py              # Parser config
│   ├── document_parser.py     # .doc/.docx parser
│   ├── word_parser.py         # Word document parser
│   ├── pdf_parser.py          # PDF parser
│   ├── excel_parser.py        # Excel parser
│   ├── image_parser.py        # Image OCR parser (PaddleOCR-VL)
│   ├── media_parser.py        # Audio/Video parser
│   ├── website_parser.py      # Website/URL parser
│   └── summary_service.py     # AI summary generation
│
├── migrations/                # Alembic DB migrations
│   ├── env.py                 # Alembic environment config
│   ├── script.py.mako         # Migration template
│   └── versions/              # Migration files (31 versions)
│
└── tests/                     # Test files
    ├── create_user.py
    ├── test_task_file_list.py
    ├── test_summary_service_integration.py
    └── test_country_tech_stats.py
```

## Prerequisites

- Python 3.12+
- PostgreSQL 14+
- Redis
- (Optional) MQTT Broker (Eclipse Mosquitto)

## Installation & Running

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd general-chatbot-api

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit the `.env` file with appropriate values:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URI` | PostgreSQL connection string (asyncpg) | `postgresql+asyncpg://postgres:123456@localhost:5433/tms` |
| `API_KEY` | API key | - |
| `API_SECRET` | API secret | - |
| `BASE_URL` | Service base URL | `http://localhost:8000` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379` |
| `LOG_LEVEL` | Log level | `INFO` |
| `DB_POOL_SIZE` | DB connection pool size | `5` |
| `DB_MAX_OVERFLOW` | DB max overflow connections | `10` |
| `PADDLEOCR_VL_SERVER_URL` | (Optional) vLLM server for OCR | - |

### 3. Initialize Database

#### Create PostgreSQL database

```bash
# Connect to PostgreSQL and create the database
psql -U postgres -p 5433
CREATE DATABASE tms;
\q
```

#### Run migrations (Alembic)

```bash
# Run all migrations
alembic upgrade head

# Show current migration
alembic current

# Show history
alembic history

# Create a new migration (after modifying models)
alembic revision --autogenerate -m "description of changes"

# Rollback 1 version
alembic downgrade -1

# Rollback to the beginning
alembic downgrade base
```

> **Note**: Alembic reads `DATABASE_URI` from `app/core/config.py` (via `.env` file). The async URL (`postgresql+asyncpg://`) is automatically converted to sync (`postgresql://`) in `migrations/env.py`.

#### Create tables directly (without migrations)

```bash
python -m app.core.init_db
```

### 4. Run the server

#### Development (with hot-reload)

```bash
python server_dev.py
# or
uvicorn server_dev:app --host 0.0.0.0 --port 8000 --reload
```

#### Production

```bash
python server.py
# or
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 2
```

### 5. Run with Docker

#### Docker Compose (full stack)

```bash
docker-compose up -d
```

This starts: API service + PostgreSQL + Redis + MQTT Broker.

#### Docker standalone

```bash
# Build image
docker build -t general-chatbot-api-environment:0.0.1 .

# Run container
bash run.sh
```

> When running Docker standalone, configure `.env.docker` with `host.docker.internal` instead of `localhost` to connect to the DB from the container.

### 6. Run the file processing job

```bash
python file_processing_job.py
```

This job processes files in the DB where `is_processed = null`, parses their content, and updates the results.

## API Endpoints

After starting the server, access Swagger UI at: **http://localhost:8000/docs**

| Prefix | Tag | Description |
|--------|-----|-------------|
| `/api/v1/login`, `/register` | Authentication | Login, registration |
| `/api/v1/users` | Users | CRUD users |
| `/api/v1/roles` | Roles | Role management |
| `/api/v1/tasks` | Tasks | Task management |
| `/api/v1/task-works` | Task Works | Work time logging |
| `/api/v1/files` | Files | Upload, query files |
| `/api/v1/kpis` | Employee KPIs | Employee KPI management |
| `/api/v1/dashboard` | Dashboard | Statistics, reports |
| `/api/v1/migration` | Database Migration | Data migration API |
| `/api/v1/chat` | Chat | Chatbot |
| `/api/v1/common` | Common API | Shared APIs |
| `/health` | - | Health check |

## Database Models

| Model | Table | Description |
|-------|-------|-------------|
| `User` | users | Users |
| `Role` | roles | Roles (hierarchical via parent_path) |
| `Task` | tasks | Tasks |
| `TaskWork` | task_works | Work time log entries |
| `File` | files | Uploaded files + metadata + parsing results |
| `EmployeeKPI` | employee_kpis | Employee KPIs |
| `Project` | projects | Projects |
| `Session` | sessions | Login sessions |
| `PersonalTaskStatus` | personal_task_statuses | Personal task statuses |
| `ChatMessage` | chat_messages | Chat messages |
| `ChatHistory` | chat_histories | Chat history |

## Database Migrations

The project uses **Alembic** to manage the database schema.

### Migration structure

```
migrations/
├── env.py              # DB connection config, imports models
├── script.py.mako      # Migration file generation template
└── versions/           # 31 migration files
    ├── e4aa627a63a7_.py                          # Initial schema
    ├── e0232010140d_.py                          # Major schema update
    ├── ed984f9db906_remove_unnecessary_table.py  # Cleanup tables
    ├── 2b58ef59915e_create_files_table.py        # Create files table
    ├── 64d643ae0e04_add_processing_fields_to_files_table.py
    ├── 2.6_add_file_classification_columns.py    # Add file classification columns
    ├── 2.7_add_processing_duration_to_files_table.py
    ├── ae938c6cdb66_add_assignee_id_to_tasks.py  # Add assignee to tasks
    ├── 053d80b23966_rename_assignee_id_to_assigned_to.py
    ├── 89bd59c367d2_create_employee_kpi_table.py # Create KPI table
    ├── 89ead7fb60dc_create_personal_task_status_table.py
    ├── c61caeb570cd_create_chatbot_tables.py     # Create chatbot tables
    ├── acdf7558aa74_add_status_field_to_users_table.py
    ├── 634d9d2868d1_add_file_name_list_to_task_table.py
    ├── 8d0430d2029f_add_is_difficult_field_to_task_works_.py
    ├── eff6d276b83c_merge_heads.py               # Merge migration branches
    └── ... (and other migrations)
```

### Workflow for creating a new migration

```bash
# 1. Modify models in app/domain/models/
# 2. Auto-generate migration
alembic revision --autogenerate -m "description of changes"

# 3. Review the generated migration file in migrations/versions/
# 4. Run the migration
alembic upgrade head
```

### Handling migration conflicts

When multiple branches create migrations in parallel:

```bash
# Merge migration heads
alembic merge heads -m "merge migration branches"

# Then run upgrade
alembic upgrade head
```

Use this workflow before pushing code that changes models or creates migrations. It helps avoid conflicting migration files and keeps each feature branch to a single migration file when possible.

1) Sync with the base branch and rebase your feature branch

```bash
git checkout <base_branch>                # e.g. develop or main
git pull origin <base_branch>
git checkout <my_branch>
git rebase <base_branch>                  # or: git merge <base_branch>
```

2) Detect migration conflicts

- Check for migration files changed/added on your branch versus the base branch:

```bash
git fetch origin
git diff --name-only origin/<base_branch>...HEAD | grep '^migrations/versions/' || true
```

- If this shows one or more files, your branch has migration files that don't exist on the base branch.

- Use Alembic to detect multiple heads (another sign of conflict):

```bash
make migrate-heads        # if it prints more than one head, migrations diverged
```

3) If conflicts exist: safely remove/recreate branch migrations

Goal: leave base migrations intact, remove only the migration files introduced by your branch, then regenerate one fresh migration on top of the updated base branch.

- Identify branch-only migration files:

```bash
BRANCH_MIGRATIONS=$(git diff --name-only origin/<base_branch>...HEAD | grep '^migrations/versions/' || true)
echo "$BRANCH_MIGRATIONS"
```

- Roll back applied migrations introduced by your branch (run once per migration file listed):

```bash
NUM=$(echo "$BRANCH_MIGRATIONS" | wc -l)
for i in $(seq 1 $NUM); do
    make migrate-down   # runs `alembic downgrade -1`
done
```

- Remove only those branch migration files (safer than deleting the whole folder):

```bash
# Shows the files to be removed first
echo "$BRANCH_MIGRATIONS"
# Remove them from git (unstage/commit as appropriate)
git rm $BRANCH_MIGRATIONS
git commit -m "Remove branch autogenerated migrations to re-generate on updated base"
```

4) Rebase/apply base migrations and recreate a single migration for your branch

```bash
# Make sure DB schema matches the base branch
make migration-up

# Re-create a single migration for your branch changes
make migrate m="<short-description>"

# Apply your new migration
make migrate-up
```

5) Review, commit, and push

```bash
git add migrations/versions/*.py
git commit -m "Add migration: <short-description>"
git push origin <my_branch>
```

Tips & detection summary

- Use `git diff --name-only origin/<base_branch>...HEAD | grep '^migrations/versions/'` to see what migration files your branch added or changed.
- Use `make migrate-heads` to see whether multiple heads exist — multiple heads indicate migration branch divergence and a merge is needed (`alembic merge heads -m "merge"`).
- Prefer removing only the branch-specific migration files (via `git rm`) rather than mass-deleting the entire `migrations/versions/` folder.
- Each feature branch should ideally create at most one migration file. If multiple migrations are needed, squash them into a single revision before pushing.

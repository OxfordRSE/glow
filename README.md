# glow-core

API and Dashboard for GLOW longitudinal questionnaire data.

## Overview

This project has two components:

- **API** (`/api`) — a read-only FastAPI service that provides suppression-safe access to student questionnaire data
- **Dashboard** (`/dashboard`) — a SvelteKit app for authenticated users to view and query data via interactive charts

In local compose, the Glow services are exposed directly:
- Dashboard → `http://localhost:3000`
- API → `http://localhost:8000`

The self-hosted ODK Central stack is available behind the optional `odk` compose profile.
Its public entrypoint defaults to `http://localhost:8080` and `https://localhost:8443`.

## Quick Start

### Option 1: Devcontainer (Recommended)

For the most consistent development experience:

1. Install [Docker](https://www.docker.com/products/docker-desktop) and [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. Open this repo in VS Code
3. Click "Reopen in Container" when prompted (or use Command Palette → "Dev Containers: Reopen in Container")
4. Wait for the devcontainer to build and app services to start
5. Place your data file at `data/data.csv` (or copy from `testdata/demo_data.csv`)
6. Create users:
   ```bash
   docker compose exec api glow-api users create --admin admin
   ```

The dashboard will be available at <http://localhost:3000> and the API at <http://localhost:8000>.

The devcontainer provides:
- Python 3.12 + Node 22 pre-installed
- `uv` for fast Python package management
- Playwright with browser dependencies
- All app services running through the production-like compose base plus dev overrides

### Option 2: Docker Compose (Host-Based)

`compose.yml` now defines the production-like core stack: Glow dashboard, Glow API, Glow Postgres, and an optional ODK Central profile. Local development layers on `compose.override.yml`, which switches the API and dashboard into reload/watch mode and bind-mounts the workspace.

```bash
# Set a strong JWT secret
export GLOW_SECRET_KEY="your-strong-secret-here"

# Set a Postgres password for the local stack
export POSTGRES_PASSWORD="your-local-postgres-password"

# Place your data file (CSV or Parquet) at data/data.csv
# The API defaults to /data/data.csv inside the container

# Start the local development stack
docker compose up --build

# Start the full stack including ODK Central
docker compose --profile odk up --build

# Create the first admin user (in a separate terminal)
docker compose exec api glow-api users create --admin admin
```

The dashboard will be available at <http://localhost:3000>.

### ODK Central

The optional `odk` profile adds a self-hosted ODK Central stack using the official Central service/nginx images plus the supporting Postgres, Redis, Enketo, SMTP, and secrets services they require.

Network boundaries in the compose setup are:

- ODK Central internal services talk only on the `odk_internal` network.
- Glow Dashboard can only reach Glow API on `dashboard_api`.
- Glow API can only reach its own Postgres on `api_db`.
- The only shared route between ODK Central and Glow is `service` ↔ `api` on `odk_api`.

This keeps ODK Central isolated from the dashboard while still allowing API-mediated data flow.

## API

### Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `GLOW_DATA_PATH` | `data/data.csv` | Path to the CSV or Parquet data file |
| `GLOW_DATA_REFRESH_HOURS` | `24` | How often to reload data from disk |
| `GLOW_MIN_N` | `5` | Minimum distinct student count for suppression |
| `GLOW_SECRET_KEY` | *(insecure default)* | JWT signing secret — **must be set in production** |
| `GLOW_ALGORITHM` | `HS256` | JWT algorithm |
| `GLOW_ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Token lifetime (8 hours) |
| `GLOW_METADATA_DATABASE_URL` | `sqlite:///./metadata.db` | SQLAlchemy metadata database URL |
| `GLOW_CORS_ORIGINS` | `["*"]` | JSON list of allowed CORS origins |

### Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Health check |
| `POST` | `/auth/login` | — | Login (returns JWT) |
| `GET` | `/schools` | User | List schools with query options |
| `POST` | `/query` | User | Execute query with blanket suppression |
| `GET` | `/admin/users` | Admin | List users |
| `POST` | `/admin/users` | Admin | Create user |
| `PUT` | `/admin/users/{id}` | Admin | Update user |
| `DELETE` | `/admin/users/{id}` | Admin | Delete user |
| `GET` | `/admin/me` | User | Current user info |

Interactive documentation is available at `/docs` (Swagger UI) and `/redoc`.

### Admin CLI

```bash
# Initialise the database
glow-api db init

# List users
glow-api users list

# Create a regular user
glow-api users create alice

# Create an admin user
glow-api users create --admin bob

# Update a user
glow-api users update alice --scope '{"filters": {"school": ["Greenwood"]}}'

# Delete a user
glow-api users delete alice
```

### Suppression

N is counted as **distinct students (uid)**, not rows. 
Any materialized result cell where the contributing student count is less than `GLOW_MIN_N` is suppressed
(set to empty in the CSV output) and recorded in the `suppressions` field of the response.

### Whitelisted columns

Query columns are restricted to a whitelist to prevent data leakage:

- **Dimensions**: `school`, `yearGroup`, `class`, `sex`, `ethnicity`, `wave`, `d_city`, `d_country`
- **Measures**: `bw_wbeing_1`–`bw_wbeing_7`, `d_age`
- **Derived scores**: currently `bw_wbeing_total`

### Query Builder

The query system exposes a safe plan DSL for analytical work over the scoped student-wave table.

Supported plan steps:

- `filter`
- `derive_score`
- `pair_waves`
- `bucket_school_size`
- `aggregate`

Safety properties:

- `uid` is kept internally for suppression counts but is never a legal public grouping field
- unsupported columns fail even when they appear late in an otherwise valid plan
- aggregation is terminal
- every output metric carries an exact distinct-student count and is suppressed when `N < GLOW_MIN_N`

Developer documentation and examples live in [docs/query-builder.md](docs/query-builder.md).

## Dashboard

The SvelteKit dashboard provides:

- **Login** — JWT-based authentication
- **Home** — pre-built overview charts
- **Query Builder** — a step-based analytical query builder with built-in suppression
- **Admin** — user CRUD (admin users only)

## Development

### Configuration Files

This repo uses a centralized approach to minimize drift between dev/test/prod:

- **`compose.yml`** — production-like core stack (dashboard, API, Postgres)
  - Used by: CI smoke tests and as the base for local development
  - Defines runtime topology and network boundaries
  - Includes the optional `odk` profile for self-hosted ODK Central
- **`compose.override.yml`** — local development overrides
  - Enables source bind mounts, Vite/Uvicorn reload, and dev-friendly defaults
  - Applied automatically by `docker compose up`
- **`compose.test.yml`** — test-specific overrides
  - Deterministic secrets, tighter healthchecks, no restart policies
  - Usage: `docker compose -f compose.yml -f compose.test.yml up`
- **`.devcontainer/`** — VS Code devcontainer configuration
  - Provides tooling shell (Python 3.12, Node 22, uv, Playwright)
  - Delegates app services to `compose.yml` (no duplication)
  - Mounts Docker socket for "Docker outside of Docker"
- **`.env.example`** — documented environment variable defaults

### Devcontainer (Recommended)

The devcontainer provides a fully configured development environment. After opening in the devcontainer:

**API development:**
```bash
cd api
uv pip install -e ".[test]"
uv run pytest
```

**Dashboard development:**
```bash
cd dashboard
npm install
npm run check    # Type checking
npm run lint     # Linting
```

**Running smoke tests:**
```bash
bash scripts/smoke_compose.sh
```

### Manual Setup (without devcontainer)

**API:**
```bash
cd api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
glow-api db init
uvicorn glow_api.main:app --reload
pytest
```

**Dashboard:**
```bash
cd dashboard
npm install
npm run dev
npm run check
```

## Deployment (AWS)

See `deploy/terraform/` for infrastructure definitions (EC2 + ALB + Route53).

See `DEPLOYMENT.md` for the quick start guide using `./deploy/deploy.sh`.

The deployment uses:
- EC2 instance running Docker Compose
- Application Load Balancer with subdomain routing
- Route 53 for DNS management
- ACM for TLS certificates
- Auto-configured ODK Central integration

### Terraform variables

See `deploy/terraform/variables.tf` for all available variables. Key ones:

| Variable | Description |
|---|---|
| `image_tag` | Docker image tag (set by deploy.sh) |
| `api_secret_key` | JWT secret (set by deploy.sh from env) |
| `aws_region` | AWS region |
| `api_min_n` | Minimum N for suppression (default: 5) |
| `certificate_arn` | ACM certificate ARN for HTTPS (optional) |

## Data Format

Data must be in the format produced by [glow-dummies](https://github.com/OxfordRSE/glow-dummies) — a student×wave long format with columns including:

- `uid` — student identifier (used for N counting in suppression)
- `wave` — survey wave number
- `school`, `yearGroup`, `class` — school structure
- `sex`, `ethnicity` — demographics
- `d_age`, `d_city`, `d_country` — derived/custom fields
- Questionnaire items from the [#BeeWell GM Survey](https://beewellprogramme.org) (e.g. `bw_wbeing_1`–`bw_wbeing_7` for SWEMWBS wellbeing, `bw_emodies_1`–`bw_emodies_10` for emotional difficulties, and ~120 further items — see [beewell_model.toml](https://github.com/OxfordRSE/glow-dummies/blob/main/examples/beewell_model.toml) for the complete list)

Generate sample data:

```bash
glow_dummies --config examples/beewell_model.toml --seed 42 --output csv > data/data.csv
```

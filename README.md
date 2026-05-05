# ib-ox-core

API and Dashboard for IB-Oxford longitudinal questionnaire data.

## Overview

This project has two components:

- **API** (`/api`) — a read-only FastAPI service that provides suppression-safe access to student questionnaire data
- **Dashboard** (`/dashboard`) — a SvelteKit app for authenticated users to view and query data via interactive charts

In development, both are served through an nginx proxy:
- Dashboard → `http://localhost:5173`
- API → `http://localhost:5173/api`

## Quick Start (Docker Compose)

`docker-compose.yml` is configured for local development: the API runs with reload enabled, the dashboard runs the Vite dev server, and both services bind-mount the local workspace so edits are reflected without rebuilding the images.

```bash
# Set a strong JWT secret
export IB_OX_SECRET_KEY="your-strong-secret-here"

# Place your data file (CSV or Parquet) in a Docker volume or bind-mount
# The API defaults to /data/data.csv inside the container

# Start the local development stack
docker compose up --build

# Create the first admin user (in a separate terminal)
docker compose exec api ib-ox-api users create --admin admin
```

The dashboard will be available at <http://localhost:5173>.

## API

### Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `IB_OX_DATA_PATH` | `data/data.csv` | Path to the CSV or Parquet data file |
| `IB_OX_DATA_REFRESH_HOURS` | `24` | How often to reload data from disk |
| `IB_OX_MIN_N` | `5` | Minimum distinct student count for suppression |
| `IB_OX_SECRET_KEY` | *(insecure default)* | JWT signing secret — **must be set in production** |
| `IB_OX_ALGORITHM` | `HS256` | JWT algorithm |
| `IB_OX_ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Token lifetime (8 hours) |
| `IB_OX_DATABASE_URL` | `sqlite:///./auth.db` | SQLAlchemy database URL |
| `IB_OX_CORS_ORIGINS` | `["*"]` | JSON list of allowed CORS origins |

### Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Health check |
| `POST` | `/auth/login` | — | Login (returns JWT) |
| `GET` | `/data/columns` | User | List available column names |
| `GET` | `/query/catalog` | User | Query Builder catalog for safe steps and autocomplete |
| `POST` | `/query` | User | Query Builder plan execution |
| `GET` | `/admin/users` | Admin | List users |
| `POST` | `/admin/users` | Admin | Create user |
| `PUT` | `/admin/users/{id}` | Admin | Update user |
| `DELETE` | `/admin/users/{id}` | Admin | Delete user |
| `GET` | `/admin/me` | User | Current user info |

Interactive documentation is available at `/docs` (Swagger UI) and `/redoc`.

### Admin CLI

```bash
# Initialise the database
ib-ox-api db init

# List users
ib-ox-api users list

# Create a regular user
ib-ox-api users create alice

# Create an admin user
ib-ox-api users create --admin bob

# Update a user
ib-ox-api users update alice --scope '{"filters": {"school": ["Greenwood"]}}'

# Delete a user
ib-ox-api users delete alice
```

### Suppression

N is counted as **distinct students (uid)**, not rows. Any materialized result cell where the contributing student count is less than `IB_OX_MIN_N` is suppressed (set to empty in the CSV output) and recorded in the `suppressions` field of the response.

### Whitelisted columns

Query columns are restricted to a whitelist to prevent data leakage:

- **Dimensions**: `school`, `yearGroup`, `class`, `sex`, `ethnicity`, `wave`, `d_city`, `d_country`
- **Measures**: `phq9_1`–`phq9_9`, `d_age`
- **Derived scores**: currently `phq9_total`

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
- every output metric carries an exact distinct-student count and is suppressed when `N < IB_OX_MIN_N`

Developer documentation and examples live in [docs/query-builder.md](docs/query-builder.md).

## Dashboard

The SvelteKit dashboard provides:

- **Login** — JWT-based authentication
- **Home** — pre-built overview charts
- **Query Builder** — a step-based analytical query builder with built-in suppression
- **Admin** — user CRUD (admin users only)

## Development

### API

```bash
cd api
pip install -e ".[test]"
# Initialise DB
ib-ox-api db init
# Start development server
uvicorn ib_ox_api.main:app --reload
# Run tests
pytest
```

### Dashboard

```bash
cd dashboard
npm install
npm run dev
```

## Deployment (AWS)

See `terraform/` for infrastructure definitions (ECS Fargate + ALB + ECR + EFS).

```bash
# Deploy version 0.1.0 (base semver must match API version in pyproject.toml)
export IB_OX_SECRET_KEY="your-production-secret"
./deploy.sh 0.1.0

# Or with a pre-release suffix
./deploy.sh 0.1.0-beta1
```

The `deploy.sh` script:
1. Checks required tools (`aws`, `terraform`, `docker`, `curl`, `jq`, `python3`)
2. Validates the deploy version against the API version
3. Authenticates with AWS SSO
4. Creates an S3 bucket for Terraform state + deploy lockfile
5. Resolves lockfile conflicts interactively
6. Builds and pushes Docker images to ECR (immutable tags — no `latest`)
7. Runs `terraform apply` interactively
8. Updates the remote lockfile

### Required environment variables for deploy

| Variable | Description |
|---|---|
| `IB_OX_SECRET_KEY` | JWT secret for production |
| `AWS_REGION` | AWS region (default: `eu-west-2`) |

### Terraform variables

See `terraform/variables.tf` for all available variables. Key ones:

| Variable | Description |
|---|---|
| `image_tag` | Docker image tag (set by deploy.sh) |
| `api_secret_key` | JWT secret (set by deploy.sh from env) |
| `aws_region` | AWS region |
| `api_min_n` | Minimum N for suppression (default: 5) |
| `certificate_arn` | ACM certificate ARN for HTTPS (optional) |

## Data Format

Data must be in the format produced by [ib-ox-dummies](https://github.com/OxfordRSE/ib-ox-dummies) — a student×wave long format with columns including:

- `uid` — student identifier (used for N counting in suppression)
- `wave` — survey wave number
- `school`, `yearGroup`, `class` — school structure
- `sex`, `ethnicity` — demographics
- `d_age`, `d_city`, `d_country` — derived/custom fields
- Questionnaire items from the [#BeeWell GM Survey](https://beewellprogramme.org) (e.g. `bw_wbeing_1`–`bw_wbeing_7` for SWEMWBS wellbeing, `bw_emodies_1`–`bw_emodies_10` for emotional difficulties, and ~120 further items — see [beewell_model.toml](https://github.com/OxfordRSE/ib-ox-dummies/blob/main/examples/beewell_model.toml) for the complete list)

Generate sample data:

```bash
ib_ox_dummies --config examples/beewell_model.toml --seed 42 --output csv > data/data.csv
```

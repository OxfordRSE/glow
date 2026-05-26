# ODK Central Integration Implementation Plan

**Status**: Ready for implementation  
**Date**: 2026-05-26  
**Version**: 1.0

---

## Executive Summary

This document outlines the complete implementation plan for integrating ODK Central into the Glow deployment pipeline, including automated project creation, user management, role assignment, and form deployment with version tracking.

### Key Features
- **Permanent admin user** with strong password rotation
- **API integration user** with minimal (viewer) permissions
- **Automated form deployment** from version control
- **Form version tracking** via JSON state file
- **Idempotent operations** for safe re-runs
- **Security-first credential isolation** (admin creds never in containers)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Security Model](#security-model)
3. [File Structure](#file-structure)
4. [Key Decisions](#key-decisions)
5. [Implementation Checklist](#implementation-checklist)
6. [Script Evaluation: Bash vs Python](#script-evaluation-bash-vs-python)
7. [Files to Remove](#files-to-remove)
8. [Testing Plan](#testing-plan)
9. [Operational Procedures](#operational-procedures)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ DEPLOYMENT TIME (terraform/deploy.sh)                       │
├─────────────────────────────────────────────────────────────┤
│ 1. Check dependencies (terraform, aws, ssh, curl, jq)      │
│ 2. Create S3 backend bucket                                 │
│ 3. terraform init + apply (EC2, ALB, security groups)       │
│ 4. Upload compose files + scripts to EC2                    │
│ 5. SSH into EC2 → run activate-stack.sh                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ ACTIVATION TIME (scripts/activate-stack.sh on EC2)          │
├─────────────────────────────────────────────────────────────┤
│ 1. Install Docker + Docker Compose                          │
│ 2. Check/install dependencies (curl, jq, xmllint)           │
│ 3. Generate runtime secrets → .env.runtime                  │
│ 4. Generate admin credentials → .deploy/.env.admin          │
│ 5. Start docker-compose stack (--profile odk)               │
│ 6. Wait for ODK Central to be ready                         │
│ 7. Configure ODK:                                            │
│    - Create/rotate admin user (glow-admin@domain)           │
│    - Create project "GLOW Data Collection"                  │
│    - Create API user (glow-api@domain) with viewer role     │
│    - Process forms from odk-forms/ directory:               │
│      • Convert XLSForm → XML (via pyxform container)        │
│      • Extract xmlFormId from XML                           │
│      • Check hash against .deploy/share/odk-forms-state.json│
│      • Upload if new/changed                                │
│    - Update state file with hashes + timestamps             │
│ 8. Restart API container with ODK credentials               │
│ 9. Verify stack health                                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ RUNTIME (Containers)                                         │
├─────────────────────────────────────────────────────────────┤
│ • API container reads .env.runtime (NOT .deploy/.env.admin) │
│ • API has viewer access to ODK via glow-api@domain          │
│ • Dashboard does NOT load .env.runtime (no ODK access)      │
│ • Forms tracked in .deploy/share/odk-forms-state.json       │
│   (mounted read-only in API container for future use)       │
└─────────────────────────────────────────────────────────────┘
```

---

## Security Model

### Credential Isolation

| Credential Type | Storage Location | Permissions | Accessible By |
|----------------|------------------|-------------|---------------|
| **ODK Admin** | `deploy/.deploy/.env.admin` | 600 (rw-------) | Host only (activate-stack.sh, rotation scripts) |
| **API User** | `deploy/.deploy/share/.env.runtime` | 600 (rw-------) | API container only (NOT Dashboard) |
| **Postgres** | `deploy/.deploy/share/.env.runtime` | 600 (rw-------) | API + API-DB containers |
| **Glow Secrets** | `deploy/.deploy/share/.env.runtime` | 600 (rw-------) | API + Dashboard containers |

### Password Strength

- **Admin password**: 64 bytes base64 (~85 characters) - within bcrypt limits
- **API user password**: 24 bytes base64 (~32 characters)
- **All passwords**: Cryptographically random via `openssl rand`

### Admin Password Rotation

- **Default behavior**: Rotate on every `activate-stack.sh` run
- **Skip rotation**: Set `NO_ROTATE_ADMIN=true` environment variable
- **Use case**: Production deployments may want stable admin password

### User Roles

| User | Email | Role | Permissions |
|------|-------|------|-------------|
| **Admin** | `glow-admin@${DOMAIN}` | Administrator | Full ODK Central access (project/user/form management) |
| **API Integration** | `glow-api@${DOMAIN}` | Viewer | Read-only: list forms, read submissions (project-scoped) |

---

## File Structure

### New Directory Structure (FINAL)

```
glow/
├── deploy/                           # NEW: All deployment-related files
│   ├── .deploy/                      # NEW: Runtime deployment artifacts
│   │   ├── .env.admin                # NEW: Admin credentials (host-only, 600)
│   │   └── share/                    # NEW: Container-mounted state files
│   │       ├── .gitkeep              # NEW: Ensure tracked in git
│   │       ├── .env.runtime          # MOVED: Runtime env (loaded by containers, 600)
│   │       └── odk-forms-state.json  # NEW: Form version tracking (644)
│   │
│   ├── terraform/                    # MOVED from root terraform/
│   │   ├── *.tf                      # MOVED: All terraform files
│   │   ├── terraform.tfvars.example  # MOVED
│   │   └── README.md                 # MODIFY: Update paths
│   │
│   ├── scripts/                      # MOVED from root scripts/
│   │   ├── activate-stack.sh         # MOVED + MODIFY: Add ODK configuration
│   │   ├── odk-api-helper.sh         # NEW: HTTP API wrapper functions (~300 lines)
│   │   ├── rotate-api-password.sh    # NEW: Password rotation tool (~100 lines)
│   │   └── smoke_compose.sh          # MOVED: Unchanged
│   │
│   ├── odk-forms/                    # NEW: Form definitions directory
│   │   ├── README.md                 # NEW: Form management documentation
│   │   └── .gitkeep                  # NEW: Ensure tracked in git
│   │
│   ├── deploy.sh                     # MOVED from terraform/deploy.sh + MODIFY
│   └── ODK_INTEGRATION_PLAN.md       # MOVED from terraform/ (this document)
│
├── api/                              # Unchanged
├── dashboard/                        # Unchanged
├── odk-central/                      # Unchanged (README.md kept for reference)
├── data/                             # Unchanged
├── compose.yml                       # MODIFY: Update volume mounts, env_file paths
├── .env.example                      # MODIFY: Document ODK env vars
├── .gitignore                        # MODIFY: Add deploy/.deploy/* patterns
└── DEPLOYMENT.md                     # MODIFY: Document ODK integration workflow
```

### Files to CREATE

| File | Description | Lines |
|------|-------------|-------|
| `deploy/.deploy/share/.gitkeep` | Ensure directory tracked | 0 |
| `deploy/.deploy/share/odk-forms-state.json` | Form version tracking | ~10 |
| `deploy/odk-forms/README.md` | Form management docs | ~80 |
| `deploy/odk-forms/.gitkeep` | Ensure directory tracked | 0 |
| `deploy/scripts/odk-api-helper.sh` | HTTP API wrapper functions | ~300 |
| `deploy/scripts/rotate-api-password.sh` | Password rotation tool | ~100 |
| `deploy/ODK_INTEGRATION_PLAN.md` | This document (moved) | 1200+ |

### Files to MOVE

| Current Path | New Path | Modifications |
|-------------|----------|---------------|
| `terraform/*` | `deploy/terraform/*` | Update internal path references |
| `terraform/deploy.sh` | `deploy/deploy.sh` | Update paths to terraform/, scripts/ |
| `terraform/ODK_INTEGRATION_PLAN.md` | `deploy/ODK_INTEGRATION_PLAN.md` | This file |
| `scripts/*` | `deploy/scripts/*` | Update WORK_DIR paths |

### Files to MODIFY

| File | Changes |
|------|---------|
| `deploy/scripts/activate-stack.sh` | Add ODK configuration logic (~300 new lines) |
| `deploy/deploy.sh` | Update paths, add --verbose flag |
| `compose.yml` | Change env_file to `./deploy/.deploy/share/.env.runtime`, update volume mounts |
| `.gitignore` | Add `deploy/.deploy/*` except `.gitkeep` and `.env.runtime` |
| `.env.example` | Document ODK environment variables |
| `DEPLOYMENT.md` | Add ODK integration section, update paths |
| `.github/workflows/ci.yml` | Update smoke_compose.sh path to `deploy/scripts/smoke_compose.sh` |

### Files to DELETE

| File | Reason |
|------|--------|
| `/home/matt/oxrse/glow/glow/deploy.sh` | Old ECS/ECR deployment, superseded by deploy/deploy.sh |
| `/home/matt/oxrse/glow/glow/nginx-ecs.conf` | ECS-specific, not needed for EC2+ALB |

---

## Key Decisions

### 1. Admin User Management

| Decision | Rationale |
|----------|-----------|
| **Permanent admin user** | ODK CLI has no `user-demote` command; temporary admin cannot be fully removed via CLI |
| **Admin email**: `glow-admin@${DOMAIN}` | Clear, distinguishable from system email |
| **Password rotation by default** | Fresh credentials on each deployment; opt-out via flag |
| **Storage**: `.deploy/.env.admin` | Host-only access, never loaded into containers |

### 2. API User Management

| Decision | Rationale |
|----------|-----------|
| **Creation method**: HTTP API | Admin already exists, HTTP API more consistent with other operations |
| **Role**: Viewer (roleId=2) | Minimal permissions - read forms/submissions only |
| **Storage**: `.env.runtime` | Loaded by API container at runtime |

### 3. Form Management

| Decision | Rationale |
|----------|-----------|
| **Support both .xml and .xlsx** | Developers prefer XLSForm (.xlsx), but .xml allows direct editing |
| **XLSForm conversion**: Pipe to pyxform via `docker compose exec` | Leverages existing pyxform container, no new dependencies |
| **Tracking**: JSON file keyed by xmlFormId | More flexible than envvar, supports metadata, parseable by Python |
| **Upload logic**: Check both ODK + hash | Idempotent - avoids unnecessary version creation |
| **Failed forms**: Retry 3x, log + summary | Resilient to transient failures, clear reporting |

### 4. Project Management

| Decision | Rationale |
|----------|-----------|
| **Default project name**: "GLOW Data Collection" | Clear, descriptive, not environment-specific |
| **Creation**: Auto-create, idempotent | Check for existing project by name, reuse if found |
| **Storage**: Cache project ID in `.deploy/.env.admin` | Faster re-runs, fewer API queries |

### 5. State Tracking

**`.deploy/share/odk-forms-state.json` structure:**

```json
{
  "simple-survey": {
    "hash": "a3f2c1e9b8d7...",
    "filename": "simple-survey.xlsx",
    "uploaded": "2026-05-26T12:34:56Z",
    "odkVersion": "1.0"
  },
  "complex-form": {
    "hash": "def456abc123...",
    "filename": "complex.xml",
    "uploaded": "2026-05-26T12:35:12Z",
    "odkVersion": "2.1"
  }
}
```

**Rationale**: 
- Keyed by `xmlFormId` (ODK's canonical identifier)
- Tracks source filename for debugging
- Timestamp for audit trail
- ODK version for compatibility tracking

### 6. Verbosity & Logging

| Decision | Rationale |
|----------|-----------|
| **Flag location**: `deploy.sh --verbose` | User-facing script, passes `VERBOSE=1` to downstream scripts |
| **Verbose mode**: Shows full curl output, API responses | Essential for debugging, opt-in to avoid clutter |
| **Default mode**: Minimal logging, clean output | Production-friendly |

---

## Implementation Checklist

### Phase 0: Repository Reorganization ✅

**Objective**: Move all deployment-related files into `deploy/` directory

- [ ] Create `deploy/` directory structure:
  ```bash
  mkdir -p deploy/.deploy/share
  mkdir -p deploy/terraform
  mkdir -p deploy/scripts
  mkdir -p deploy/odk-forms
  ```

- [ ] Move existing files:
  ```bash
  # Move terraform files
  git mv terraform/* deploy/terraform/
  
  # Move scripts
  git mv scripts/* deploy/scripts/
  
  # Move deployment script
  git mv terraform/deploy.sh deploy/deploy.sh
  
  # Move this plan document
  git mv terraform/ODK_INTEGRATION_PLAN.md deploy/ODK_INTEGRATION_PLAN.md
  ```

- [ ] Update paths in moved files:
  - [ ] `deploy/deploy.sh`: Update `SCRIPT_DIR` and `TERRAFORM_DIR` paths
  - [ ] `deploy/scripts/activate-stack.sh`: Update `WORK_DIR="/opt/glow"` (unchanged, still runs on EC2)
  - [ ] `deploy/terraform/README.md`: Update documentation paths

- [ ] Update root-level file references:
  - [ ] `compose.yml`: Update env_file and volume paths
  - [ ] `.github/workflows/ci.yml`: Update smoke_compose.sh path
  - [ ] `DEPLOYMENT.md`: Update all deployment path references

- [ ] Update `.gitignore`:
  ```gitignore
  # Deployment artifacts (in deploy/.deploy/)
  deploy/.deploy/*
  !deploy/.deploy/share/
  deploy/.deploy/share/*
  !deploy/.deploy/share/.gitkeep
  !deploy/.deploy/share/.env.runtime
  
  # Existing patterns
  .env
  *.db
  ```

- [ ] Remove old directories (after move completes):
  ```bash
  git rm -r terraform/
  git rm -r scripts/
  ```

### Phase 1: Directory Structure & Files ✅

- [ ] Create `.deploy/` subdirectories:
  ```bash
  cd deploy
  mkdir -p .deploy/share
  touch .deploy/share/.gitkeep
  touch odk-forms/.gitkeep
  ```

- [ ] Create initial state files:
  ```bash
  # Initial (empty) form state
  echo '{}' > deploy/.deploy/share/odk-forms-state.json
  ```

- [ ] Verify structure:
  ```bash
  tree deploy/ -a -I '.git'
  # Should show complete deploy/ structure
  ```

### Phase 2: ODK API Helper Script ✅

**File**: `scripts/odk-api-helper.sh` (~300-400 lines)

**Functions to implement:**

```bash
# Authentication
odk_login(email, password) -> token

# Project management
odk_create_project(token, name, description) -> project_id
odk_get_project_by_name(token, name) -> project_id or empty

# User management
odk_create_user(token, email, password) -> user_id
odk_get_user_actor_id(token, email) -> actor_id

# Role assignment
odk_assign_role(token, project_id, role_id, actor_id) -> success

# Form management
odk_list_forms(token, project_id) -> json_array
odk_upload_form(token, project_id, form_xml_content) -> xmlFormId

# Utilities
get_form_hash(file_path) -> sha256_hash
convert_xlsform_to_xml(xlsx_file_path) -> xml_content
extract_xmlformid_from_xml(xml_content) -> xmlFormId
```

**Implementation notes:**
- Use `curl --retry 3 --retry-delay 5 --fail --silent --show-error`
- Check `$VERBOSE` envvar for `-v` flag on curl
- Return meaningful exit codes (0=success, 1+=failure)
- Log all operations with timestamps
- Internal API URL: `http://service:8383`

### Phase 3: Update activate-stack.sh ✅

**Modify `generate_runtime_env()` function:**
- Remove `ODK_ADMIN_PASSWORD` from `.env.runtime`
- Create `.deploy/.env.admin` with admin credentials
- Create `.deploy/share/odk-forms-state.json` initialized to `{}`
- Set file permissions appropriately

**Rewrite `configure_odk()` function (~200 lines):**
- Source `odk-api-helper.sh`
- Handle admin password rotation (check `NO_ROTATE_ADMIN` flag)
- Create/promote admin user via CLI
- Authenticate admin via HTTP API
- Create/get default project
- Create API user via HTTP API
- Assign viewer role to API user
- Call `process_forms()`
- Store credentials and IDs in appropriate files

**Add `process_forms()` function (~150 lines):**
- Iterate over `odk-forms/*.{xml,xlsx,xls}`
- Validate file exists and is readable
- Convert XLSForm → XML if needed (via pyxform container)
- Extract xmlFormId from XML
- Calculate SHA256 hash
- Check against `.deploy/share/odk-forms-state.json`
- Check if exists in ODK Central
- Upload if new or changed (with 3 retries)
- Update state file with metadata
- Track failed uploads for summary report

**Add `check_dependencies()` function:**
- Check for: curl, jq, xmllint, openssl, sha256sum
- Auto-install via yum if missing
- Exit if installation fails

**Update `main()` function:**
- Call `check_dependencies()` first
- Pass through `NO_ROTATE_ADMIN` environment variable

### Phase 4: Create Password Rotation Script ✅

**File**: `scripts/rotate-api-password.sh` (~100 lines)

```bash
#!/usr/bin/env bash
# Rotate ODK API integration user password

set -euo pipefail

WORK_DIR="/opt/glow"
RUNTIME_ENV="${WORK_DIR}/.env.runtime"

# Source helpers and admin creds
source "${WORK_DIR}/scripts/odk-api-helper.sh"
source "${WORK_DIR}/.deploy/.env.admin"

# Generate new password
new_password="$(openssl rand -base64 24 | tr -d '\n')"

# Authenticate as admin
admin_token=$(odk_login "$ODK_ADMIN_EMAIL" "$ODK_ADMIN_PASSWORD")

# Get API user email from .env.runtime
api_user_email=$(grep ODK_API_EMAIL "$RUNTIME_ENV" | cut -d= -f2)

# Use ODK CLI to set password
docker compose --env-file "$RUNTIME_ENV" --profile odk exec -T service \
  node /usr/odk/lib/bin/cli.js user-set-password \
  --email "$api_user_email" \
  --password "$new_password"

# Update .env.runtime
sed -i "s|^ODK_API_PASSWORD=.*|ODK_API_PASSWORD=${new_password}|" "$RUNTIME_ENV"

# Restart API container
docker compose --env-file "$RUNTIME_ENV" up -d --force-recreate api

echo "✓ API user password rotated and container restarted"
```

### Phase 5: Update deploy.sh ✅

**Add at beginning:**

```bash
# Parse flags
VERBOSE=0
NO_ROTATE_ADMIN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verbose) VERBOSE=1; shift ;;
    --no-rotate-admin) NO_ROTATE_ADMIN=true; shift ;;
    *) shift ;;
  esac
done

export VERBOSE
export NO_ROTATE_ADMIN

# Enhanced dependency check
check_tools() {
  local missing=()
  for tool in aws terraform ssh scp curl jq; do
    ! command -v "$tool" &>/dev/null && missing+=("$tool")
  done
  
  if [[ ${#missing[@]} -gt 0 ]]; then
    error "Missing dependencies: ${missing[*]}"
    echo "Please install them and try again"
    exit 1
  fi
}
```

**Pass environment variables to remote activation:**

```bash
# In upload_and_activate() function
ssh -i "${SSH_KEY}" ec2-user@"${EC2_IP}" \
  "cd /opt/glow && \
   VERBOSE=${VERBOSE} \
   NO_ROTATE_ADMIN=${NO_ROTATE_ADMIN} \
   sudo -E bash scripts/activate-stack.sh"
```

### Phase 6: Update compose.yml ✅

**Add volume mount and update env_file for API service:**

```yaml
api:
  build:
    context: ./api
    dockerfile: Dockerfile
  env_file: ./deploy/.deploy/share/.env.runtime  # UPDATED PATH
  volumes:
    - ./data:/data:ro
    - ./deploy/.deploy/share:/deploy:ro  # NEW: ODK state files (read-only)
  # ... rest of config unchanged
```

**Rationale**:
- `.env.runtime` now loaded from shared volume mount
- `/deploy` mount provides access to `odk-forms-state.json` for future API features
- Read-only mount prevents accidental modification

### Phase 7: Documentation ✅

**Create `odk-forms/README.md`:**
- Supported formats (.xml, .xlsx, .xls)
- How to add a new form
- How to update a form
- Version tracking explanation
- Troubleshooting tips

**Update `DEPLOYMENT.md`:**
- Add "ODK Central Integration" section
- Document credential isolation model
- Explain form management workflow
- Security notes about `.deploy/.env.admin`
- Password rotation procedures

**Update `terraform/README.md`:**
- Mention `--verbose` and `--no-rotate-admin` flags
- Document form directory location
- List credential file locations on EC2

**Update `.env.example`:**
```bash
# ─── ODK Central API Integration (Runtime - loaded by API container) ──────────

# API integration user (auto-created during deployment, viewer role)
# ODK_API_URL=https://odk.example.com
# ODK_API_EMAIL=glow-api@example.com
# ODK_API_PASSWORD=<auto-generated>
# ODK_PROJECT_ID=1

# NOTE: Admin credentials are stored in .deploy/.env.admin (host-only, NOT loaded by containers)
# Admin is used for deployment-time operations only (project/user/form management)
```

---

## Script Evaluation: Bash vs Python

### Criteria for Evaluation

| Factor | Weight | Bash Advantage | Python Advantage |
|--------|--------|----------------|------------------|
| Deployment simplicity | HIGH | ✅ No extra deps | ❌ Requires Python on EC2 |
| Error handling | MEDIUM | ⚠️ Complex | ✅ Try/except, clear |
| JSON manipulation | HIGH | ⚠️ Needs jq | ✅ Native support |
| HTTP API calls | MEDIUM | ⚠️ Needs curl | ✅ Requests library |
| Testing | MEDIUM | ⚠️ bats/shunit2 | ✅ pytest built-in |
| Maintenance | HIGH | ⚠️ Can get messy | ✅ Clearer structure |
| Execution speed | LOW | ✅ Native | ⚠️ Startup overhead |
| Docker integration | HIGH | ✅ Native exec | ✅ docker-py available |

### Script-by-Script Analysis

#### 1. `odk-api-helper.sh` (Bash) vs `odk_api_helper.py` (Python)

**Bash Implementation:**
```bash
odk_login() {
  local email="$1"
  local password="$2"
  
  local response
  response=$(curl -sf --retry 3 \
    -X POST "http://service:8383/v1/sessions" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\",\"password\":\"$password\"}")
  
  echo "$response" | jq -r '.token'
}
```

**Python Implementation:**
```python
import requests

def odk_login(email: str, password: str) -> str:
    response = requests.post(
        "http://service:8383/v1/sessions",
        json={"email": email, "password": password},
        timeout=30
    )
    response.raise_for_status()
    return response.json()["token"]
```

**Decision**: ⚖️ **BASH** 

**Rationale**:
- Already requires curl/jq for deploy.sh
- No new dependencies on EC2
- Simpler for shell script integration
- Called from bash scripts anyway (activate-stack.sh)
- JSON handling with jq is adequate for simple operations

**Trade-off**: More verbose error handling, but manageable for this use case.

---

#### 2. `activate-stack.sh` (Bash) vs `activate_stack.py` (Python)

**Complexity comparison:**
- Docker compose exec calls: 20+ lines
- File operations: 15+ lines  
- Conditional logic: 30+ lines
- Logging/formatting: 10+ lines

**Bash advantages:**
- Native docker/compose integration
- Already established pattern
- No Python dependency needed on EC2
- Easier to run with sudo

**Python advantages:**
- Better error handling
- Cleaner JSON state file manipulation
- More testable
- Type safety

**Decision**: ⚖️ **BASH**

**Rationale**:
- Existing pattern in codebase
- Heavy use of `docker compose exec` - native in bash
- Would need to shell out to docker anyway in Python
- EC2 may not have Python pre-installed (Amazon Linux minimal)
- Script runs once during deployment (not performance-critical)

**Mitigation**: 
- Use functions liberally to improve readability
- Add comprehensive comments
- Strict error handling (`set -euo pipefail`)

---

#### 3. `rotate-api-password.sh` (Bash) vs `rotate_api_password.py` (Python)

**Operations:**
- Read env files
- Call ODK API via helper
- Update env file (sed)
- Restart container

**Decision**: ⚖️ **BASH**

**Rationale**:
- Depends on `odk-api-helper.sh` (bash)
- Simple linear script (~100 lines)
- File manipulation with sed is straightforward
- Consistent with activate-stack.sh

---

#### 4. `terraform/deploy.sh` (Bash) vs `deploy.py` (Python Click)

**Current state**: Already bash, works well

**Python Click alternative:**
```python
import click

@click.command()
@click.option('--verbose', is_flag=True, help='Enable verbose output')
@click.option('--no-rotate-admin', is_flag=True, help='Skip admin password rotation')
def deploy(verbose, no_rotate_admin):
    """Deploy Glow infrastructure to AWS"""
    # ...
```

**Decision**: ⚖️ **KEEP BASH**

**Rationale**:
- Already implemented and working
- Terraform/AWS CLI calls are shell-native
- SSH operations cleaner in bash
- Adding Python adds deployment dependency
- No compelling advantage for this use case

---

### Summary: All Scripts → Bash

| Script | Decision | Primary Rationale |
|--------|----------|-------------------|
| `odk-api-helper.sh` | **Bash** | No new dependencies, adequate JSON handling with jq |
| `activate-stack.sh` | **Bash** | Native docker integration, existing pattern |
| `rotate-api-password.sh` | **Bash** | Simple script, consistency with ecosystem |
| `terraform/deploy.sh` | **Bash** | Already working, shell-native operations |

**Future consideration**: If API container needs to interact with ODK state programmatically (e.g., reading form metadata), create a Python module in `api/` for that specific use case.

---

## Files to Remove

### Analysis

After reviewing the codebase structure, the following files are candidates for removal:

#### 1. `/home/matt/oxrse/glow/glow/deploy.sh` (Root-level)

**Status**: ⚠️ **INVESTIGATE BEFORE REMOVING**

**Reason**: 
- May conflict with `terraform/deploy.sh`
- Different deployment approach (appears to be older ECS/ECR-based)
- Contains version checking and lockfile logic not present in terraform/deploy.sh

**Recommendation**: 
```bash
# Before removal, verify:
1. Check if any CI/CD references it
2. Check if any documentation mentions it
3. Compare functionality with terraform/deploy.sh
4. If deprecated, rename to deploy.sh.deprecated for archive
```

**Question for user**: Is `/home/matt/oxrse/glow/glow/deploy.sh` still used, or was it replaced by `terraform/deploy.sh`?

---

#### 2. Deprecated ECS/ECR Configuration Files

**Potential candidates** (need to verify existence):
- `nginx-ecs.conf` (root level) - Likely for ECS deployment
- Any `ecs-*.tf` terraform files
- Any `ecr-*.tf` terraform files
- Dockerrun.aws.json or similar ECS task definitions

**Status**: ⚠️ **VERIFY USAGE**

**Recommendation**: Search for actual usage before removal.

---

#### 3. Legacy Python Deployment Package

**Status**: ✅ **CONFIRMED REMOVED** (from previous work)

The `glow_deploy/` Python package was already removed in earlier work per the progress summary.

---

### Removal Checklist

Before removing any file:

- [ ] Search codebase for references: `git grep -i "filename"`
- [ ] Check git history: `git log --all --full-history -- path/to/file`
- [ ] Verify not referenced in CI/CD (check `.github/workflows/`)
- [ ] Verify not mentioned in documentation
- [ ] Consider deprecation marker instead of deletion (`.deprecated` suffix)

---

## Testing Plan

### 1. Local Development Testing

**Prerequisites:**
- Docker + Docker Compose installed
- ODK profile enabled: `docker compose --profile odk up`

**Test cases:**

```bash
# Test 1: XLSForm conversion
cat test-form.xlsx | docker compose exec -T pyxform \
  sh -c 'curl --request POST --data-binary @- http://localhost:80/api/v1/convert' | jq

# Test 2: XML extraction
echo '<data id="test-form">...</data>' | xmllint --xpath 'string(//*[local-name()="data"]/@id)' -

# Test 3: JSON state file manipulation
echo '{}' > test-state.json
jq '.["form1"] = {"hash":"abc","uploaded":"2026-05-26T12:00:00Z"}' test-state.json
```

### 2. First Deployment Test

**Setup:**
1. Ensure `terraform.tfvars` configured
2. Place test form in `odk-forms/test-survey.xlsx`
3. Run deployment:
   ```bash
   cd terraform
   ./deploy.sh --verbose
   ```

**Verify:**
- [ ] `.deploy/.env.admin` created on EC2 (check via SSH)
- [ ] `.deploy/share/odk-forms-state.json` created
- [ ] Admin user `glow-admin@${DOMAIN}` exists in ODK Central
- [ ] Project "GLOW Data Collection" created
- [ ] API user `glow-api@${DOMAIN}` exists
- [ ] API user has viewer role on project
- [ ] Test form uploaded to ODK Central
- [ ] Form hash recorded in state file
- [ ] API container can authenticate to ODK
- [ ] Dashboard does NOT have ODK credentials in environment

**Commands to verify:**
```bash
# SSH into EC2
ssh -i ~/.ssh/glow-key.pem ec2-user@<EC2_IP>

# Check admin credentials file
sudo cat /opt/glow/.deploy/.env.admin

# Check state file
cat /opt/glow/.deploy/share/odk-forms-state.json | jq

# Check API container env (should have ODK_API_*, NOT ODK_ADMIN_*)
sudo docker compose exec api env | grep ODK

# Check Dashboard container env (should NOT have any ODK_*)
sudo docker compose exec dashboard env | grep ODK
```

### 3. Idempotency Test (Re-run)

**Scenario**: Re-run deployment without changes

```bash
cd terraform
./deploy.sh --no-rotate-admin
```

**Expected behavior:**
- [ ] Admin password NOT rotated (kept from first run)
- [ ] No duplicate projects created
- [ ] No duplicate users created
- [ ] Forms NOT re-uploaded (hash unchanged)
- [ ] Logs show "already exists" / "unchanged" messages
- [ ] All services remain healthy

### 4. Password Rotation Test

**Scenario A**: Default rotation (admin password changes)
```bash
./deploy.sh  # without --no-rotate-admin
```

**Verify:**
- [ ] New admin password in `.deploy/.env.admin`
- [ ] Admin can still log into ODK web UI
- [ ] API user still works

**Scenario B**: Skip rotation
```bash
./deploy.sh --no-rotate-admin
```

**Verify:**
- [ ] Admin password unchanged
- [ ] Timestamp in `.deploy/.env.admin` not updated

### 5. Form Update Test

**Scenario**: Modify existing form, add new form

```bash
# Modify existing form
vi odk-forms/test-survey.xlsx  # make changes
# Add new form
cp another-survey.xlsx odk-forms/

# Deploy
cd terraform && ./deploy.sh
```

**Verify:**
- [ ] Modified form creates new version in ODK Central
- [ ] Old version still accessible in ODK
- [ ] New form uploaded successfully
- [ ] State file updated with new hashes
- [ ] Both forms tracked in state file

### 6. Failed Form Upload Test

**Scenario**: Add invalid form file

```bash
# Create invalid XLSForm
echo "invalid" > odk-forms/broken.xlsx

# Deploy
cd terraform && ./deploy.sh
```

**Expected:**
- [ ] Deployment continues (doesn't fail)
- [ ] Inline warning shown for broken.xlsx
- [ ] Summary at end lists failed forms
- [ ] Other forms still uploaded successfully
- [ ] Broken form NOT in state file

### 7. API Password Rotation Test

**Scenario**: Rotate API user password

```bash
# SSH into EC2
ssh -i ~/.ssh/glow-key.pem ec2-user@<EC2_IP>

# Run rotation script
cd /opt/glow
sudo bash scripts/rotate-api-password.sh
```

**Verify:**
- [ ] New password in `.env.runtime`
- [ ] API container restarted
- [ ] API can still authenticate to ODK
- [ ] Old password no longer works

### 8. Security Audit Test

**Verify credential isolation:**

```bash
# On EC2 instance
ssh -i ~/.ssh/glow-key.pem ec2-user@<EC2_IP>

# Admin creds should NOT be in API container
sudo docker compose exec api env | grep ODK_ADMIN_PASSWORD
# Should return nothing

# API creds SHOULD be in API container
sudo docker compose exec api env | grep ODK_API
# Should show: ODK_API_EMAIL, ODK_API_PASSWORD, ODK_API_URL, ODK_PROJECT_ID

# Dashboard should have NO ODK variables
sudo docker compose exec dashboard env | grep ODK
# Should return nothing

# Check file permissions
ls -la /opt/glow/.deploy/.env.admin
# Should show: -rw------- (600)

ls -la /opt/glow/.deploy/share/odk-forms-state.json
# Should show: -rw-r--r-- (644)
```

---

## Operational Procedures

### Routine Deployment

```bash
# 1. Update codebase
git pull origin main

# 2. Add/update forms if needed
cp new-form.xlsx odk-forms/

# 3. Deploy
cd terraform
./deploy.sh

# Expected: 
# - Forms uploaded
# - Admin password rotated
# - Services restarted
```

### Emergency Admin Password Reset

If admin password is lost or compromised:

```bash
# SSH into EC2
ssh -i ~/.ssh/glow-key.pem ec2-user@<EC2_IP>

# Delete admin credentials file
sudo rm /opt/glow/.deploy/.env.admin

# Re-run activation (will generate new admin password)
cd /opt/glow
sudo bash scripts/activate-stack.sh

# New credentials will be in .deploy/.env.admin
sudo cat /opt/glow/.deploy/.env.admin
```

### Emergency API Password Reset

If API user password is compromised:

```bash
# SSH into EC2
ssh -i ~/.ssh/glow-key.pem ec2-user@<EC2_IP>

# Run rotation script
cd /opt/glow
sudo bash scripts/rotate-api-password.sh

# Verify API container restarted
sudo docker compose ps api
```

### Adding a New Form

```bash
# 1. Add form file to repo
cp my-new-form.xlsx odk-forms/

# 2. Commit to version control
git add odk-forms/my-new-form.xlsx
git commit -m "Add new data collection form"
git push

# 3. Deploy
cd terraform
./deploy.sh

# Form will be automatically uploaded
```

### Removing a Form

**From ODK Central:**
- Use ODK Central web UI to archive/delete form
- State file will retain entry (harmless)

**From version control:**
```bash
git rm odk-forms/old-form.xlsx
git commit -m "Remove deprecated form"
git push
```

**Note**: Removing from git does NOT remove from ODK Central - manual deletion required.

### Viewing Form Upload History

```bash
# SSH into EC2
ssh -i ~/.ssh/glow-key.pem ec2-user@<EC2_IP>

# View state file
cat /opt/glow/.deploy/share/odk-forms-state.json | jq

# Output shows:
{
  "simple-survey": {
    "hash": "a3f2c1e9...",
    "filename": "simple-survey.xlsx",
    "uploaded": "2026-05-26T12:34:56Z",
    "odkVersion": "1.0"
  }
}
```

### Checking Deployment Status

```bash
# View container logs
ssh -i ~/.ssh/glow-key.pem ec2-user@<EC2_IP>
cd /opt/glow
sudo docker compose logs -f

# Check specific service
sudo docker compose logs -f service  # ODK Central backend
sudo docker compose logs -f api      # Glow API

# Check health
sudo docker compose ps
```

---

## Appendices

### A. Environment Variable Reference

#### `.deploy/.env.admin` (Host-only)

```bash
ODK_ADMIN_EMAIL=glow-admin@example.com
ODK_ADMIN_PASSWORD=<64 bytes base64>
ODK_ADMIN_ACTOR_ID=42
ODK_PROJECT_ID=1
```

#### `.env.runtime` (Loaded by containers)

```bash
# Glow API
GLOW_SECRET_KEY=<secret>
GLOW_MIN_N=5
GLOW_DATA_PATH=/data/data.csv
GLOW_METADATA_DATABASE_URL=postgresql+psycopg://...
GLOW_CORS_ORIGINS=["https://example.com","https://api.example.com"]

# Dashboard
PUBLIC_API_BASE=https://api.example.com

# Postgres
POSTGRES_DB=glow
POSTGRES_USER=glow
POSTGRES_PASSWORD=<secret>

# ODK Central (container config)
ODK_DOMAIN=odk.example.com
ODK_SYSADMIN_EMAIL=admin@example.com  # Used by ODK Central on first boot
ODK_SSL_TYPE=upstream
ODK_HTTP_PORT=8080
ODK_HTTPS_PORT=8443

# ODK Postgres
ODK_POSTGRES_DB=odk
ODK_POSTGRES_USER=odk
ODK_POSTGRES_PASSWORD=<secret>

# ODK Central version
ODK_CENTRAL_TAG=v2026.1.2

# ODK API Integration (used by Glow API container)
ODK_API_URL=https://odk.example.com
ODK_API_EMAIL=glow-api@example.com
ODK_API_PASSWORD=<secret>
ODK_PROJECT_ID=1
```

### B. ODK Central HTTP API Quick Reference

**Base URL**: `http://service:8383` (internal) or `https://odk.${DOMAIN}` (external)

**Authentication**: Bearer token from `/v1/sessions`

```bash
# Login
POST /v1/sessions
{"email": "user@example.com", "password": "password"}
→ {"token": "...", "expiresAt": "..."}

# Create project
POST /v1/projects
{"name": "Project Name"}
→ {"id": 1, "name": "...", ...}

# List projects
GET /v1/projects
→ [{"id": 1, "name": "..."}, ...]

# Create user
POST /v1/users
{"email": "user@example.com", "password": "password"}
→ {"id": 42, "email": "...", ...}

# Get user by email
GET /v1/users?q=user@example.com
→ [{"id": 42, "email": "...", ...}]

# Assign role
POST /v1/projects/{projectId}/assignments/{roleId}/{actorId}
→ {"success": true}

# List forms
GET /v1/projects/{projectId}/forms
→ [{"xmlFormId": "...", "name": "...", ...}]

# Upload form
POST /v1/projects/{projectId}/forms?publish=true
Content-Type: application/xml
<xml form content>
→ {"xmlFormId": "...", "name": "...", ...}
```

### C. Troubleshooting Guide

#### Issue: Form upload fails with "invalid XML"

**Diagnosis:**
```bash
# Test XLSForm conversion locally
cat problem-form.xlsx | docker compose exec -T pyxform \
  sh -c 'curl --request POST --data-binary @- http://localhost:80/api/v1/convert' | jq

# Check for conversion errors
```

**Solution**: Validate form at https://getodk.org/xlsform/ before deploying

#### Issue: Admin user already exists but password unknown

**Solution**: Reset admin credentials
```bash
sudo rm /opt/glow/.deploy/.env.admin
sudo bash /opt/glow/scripts/activate-stack.sh
```

#### Issue: API container can't authenticate to ODK

**Diagnosis:**
```bash
# Check API container has credentials
sudo docker compose exec api env | grep ODK_API

# Test authentication manually
curl -X POST https://odk.example.com/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"email":"glow-api@example.com","password":"<from env>"}'
```

**Solution**: Rotate API password
```bash
sudo bash /opt/glow/scripts/rotate-api-password.sh
```

#### Issue: Form not appearing in ODK Central web UI

**Check:**
1. Correct project selected ("GLOW Data Collection")
2. User has permission to view forms
3. Form published (not draft)
4. Check deployment logs for upload errors

---

## FINAL DECISIONS (2026-05-26)

### ✅ Resolved Questions

#### 1. Directory Reorganization: `deploy/` Structure
**Decision**: APPROVED - Reorganize all deployment-related files into `deploy/` directory

**New structure:**
```
glow/
├── deploy/                           # All deployment-related files
│   ├── .deploy/                      # Runtime deployment artifacts
│   │   └── share/                    # Container-mounted state files
│   │       ├── .gitkeep
│   │       ├── .env.runtime          # MOVED HERE (loaded by containers)
│   │       └── odk-forms-state.json
│   ├── terraform/                    # Terraform infrastructure code
│   ├── scripts/                      # Deployment scripts
│   ├── odk-forms/                    # Form definitions
│   ├── deploy.sh                     # Main deployment entry point
│   └── ODK_INTEGRATION_PLAN.md       # This document
```

**Rationale**: 
- Clear separation of deployment vs application code
- All deployment artifacts in one place
- Simpler .gitignore patterns
- `.env.runtime` shared via volume mount (same as other state files)

#### 2. Files to Remove
**Decision**: DELETE COMPLETELY (no .deprecated)

- `/home/matt/oxrse/glow/glow/deploy.sh` - Old ECS/ECR deployment
- `/home/matt/oxrse/glow/glow/nginx-ecs.conf` - ECS-specific configuration

**Verification**: 
- ✅ CI/CD does NOT reference these files (checked `.github/workflows/`)
- ✅ New `deploy/deploy.sh` will replace old functionality

#### 3. .env.runtime Location
**Decision**: Move to `deploy/.deploy/share/.env.runtime`

**Rationale**:
- Consistent with other deployment state files
- Single volume mount point: `./deploy/.deploy/share:/deploy`
- API container loads from `/deploy/.env.runtime`

**compose.yml update:**
```yaml
api:
  env_file: ./deploy/.deploy/share/.env.runtime
  volumes:
    - ./data:/data:ro
    - ./deploy/.deploy/share:/deploy:ro
```

#### 4. Implementation Order
**Decision**: Reorganize → Implement → Clean

1. **Phase 1 (Reorganization)**: Create `deploy/` structure, move files
2. **Phase 2 (Implementation)**: Implement ODK integration features
3. **Phase 3 (Cleanup)**: Remove old files after verification

**Rationale**: Keeps old files as backup until new system proven working

#### 5. odk-central/README.md
**Decision**: KEEP - Documents compose stack architecture

**Rationale**: Provides detailed service configuration reference that complements high-level DEPLOYMENT.md

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-05-26 | AI Assistant | Initial comprehensive plan |

---

## Approval

- [x] Technical review complete
- [x] Security review complete  
- [x] User questions answered
- [x] **Directory reorganization approved** (`deploy/` structure)
- [x] **Files to remove identified** (deploy.sh, nginx-ecs.conf)
- [x] **Bash vs Python decision made** (all scripts use Bash)
- [x] **Ready for implementation**

---

## Implementation Summary

### Changes Overview

| Category | Changes |
|----------|---------|
| **New directories** | `deploy/`, `deploy/.deploy/`, `deploy/.deploy/share/`, `deploy/odk-forms/` |
| **Moved files** | terraform/* → deploy/terraform/, scripts/* → deploy/scripts/ |
| **New scripts** | odk-api-helper.sh (~300 lines), rotate-api-password.sh (~100 lines) |
| **Modified scripts** | activate-stack.sh (+300 lines ODK logic), deploy.sh (paths + flags) |
| **Files deleted** | deploy.sh (root), nginx-ecs.conf |
| **Config changes** | compose.yml (paths), .gitignore (deploy/ patterns), .env.example (ODK vars) |

### Implementation Order

1. **Phase 0**: Repository reorganization (create deploy/, move files)
2. **Phase 1**: Create directory structure within deploy/
3. **Phase 2**: Implement odk-api-helper.sh
4. **Phase 3**: Update activate-stack.sh with ODK integration
5. **Phase 4**: Create rotate-api-password.sh
6. **Phase 5**: Update deploy.sh with flags and dependency checks
7. **Phase 6**: Update compose.yml paths
8. **Phase 7**: Documentation (README files, DEPLOYMENT.md updates)
9. **Phase 8**: Delete old files (after testing)

### Success Criteria

- ✅ All files successfully moved to deploy/ structure
- ✅ All tests pass with new paths
- ✅ Deployment works end-to-end (local + AWS)
- ✅ ODK Central fully integrated (admin, API user, forms)
- ✅ Security model verified (credential isolation)
- ✅ Documentation updated and accurate

---

**End of Document**

# Devcontainer Setup Migration Guide

This document explains the changes made to centralize configuration and add devcontainer support.

## What Changed

### New Files

1. **`compose.yml`** (renamed from `docker-compose.yml`)
   - Canonical service specification
   - Used by all contexts (local, CI, devcontainer)

2. **`compose.test.yml`**
   - Minimal test-specific overrides
   - Stricter healthchecks, deterministic secrets

3. **`.devcontainer/`**
   - `devcontainer.json` — VS Code devcontainer config
   - `compose.yml` — Workspace container definition
   - `Dockerfile` — Tooling image (Python 3.12 + Node 22 + uv + Playwright)

4. **`.env.example`**
   - Documented environment variable defaults

### Modified Files

1. **`scripts/smoke_compose.sh`**
   - Now uses `docker compose -f compose.yml -f compose.test.yml`
   - Removed manual healthcheck polling (uses `--wait` instead)

2. **`.github/workflows/ci.yml`**
   - Updated teardown to use compose file flags

3. **`README.md`**
   - Added devcontainer quick start
   - Added configuration files section
   - Reorganized development instructions

### Removed Files

- `docker-compose.yml` → renamed to `compose.yml`
- Old version backed up as `docker-compose.yml.old`

## Design Principles

1. **Single source of truth**: `compose.yml` defines all app services
2. **Minimal overlays**: Only explicit differences in test/dev configs
3. **No duplication**: Devcontainer reuses app services, doesn't redefine them
4. **Close to prod**: Same runtime model across local/CI/prod

## Migration Path

### For Local Development

**Before:**
```bash
docker compose up --build
```

**After (both work):**
```bash
# Option 1: Docker Compose (same as before)
docker compose up --build

# Option 2: Devcontainer (recommended)
# Open in VS Code → "Reopen in Container"
```

### For CI

**Before:**
```bash
docker compose up --build
```

**After:**
```bash
docker compose -f compose.yml -f compose.test.yml up --build
```

### For Tests

The smoke script automatically uses the correct compose files, so no changes needed:
```bash
bash scripts/smoke_compose.sh
```

## Benefits

1. **Consistency**: Same Python/Node versions across dev and CI
2. **Faster onboarding**: One-click devcontainer setup
3. **Less drift**: Shared canonical service definitions
4. **Better tooling**: Pre-configured VS Code extensions and settings
5. **Cleaner hosts**: Fewer globally installed tools

## Rollback

If needed, restore the old setup:
```bash
mv docker-compose.yml.old docker-compose.yml
rm compose.yml compose.test.yml .env.example
rm -rf .devcontainer
git restore scripts/smoke_compose.sh .github/workflows/ci.yml README.md
```

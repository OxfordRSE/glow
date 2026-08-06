#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export GLOW_SECRET_KEY="${GLOW_SECRET_KEY:-smoke-test-secret}"

# Use canonical compose.yml + test overrides
docker compose -f compose.yml -f compose.test.yml down -v --remove-orphans
docker compose -f compose.yml -f compose.test.yml up --build -d --wait

# Healthcheck now guarantees API is ready, so seed users immediately.
# The DB is bind-mounted on the host and survives `down -v`, so schools/users
# may already exist from a previous run - tolerate that and upsert instead.
COMPOSE="docker compose -f compose.yml -f compose.test.yml exec -T api glow-api"

$COMPOSE schools create "Focus School Academy" || true
$COMPOSE schools create "Neighbouring School" || true

if ! $COMPOSE users create --admin --password admin --schools 'Focus School Academy,Neighbouring School' admin; then
  $COMPOSE users update --password admin --schools 'Focus School Academy,Neighbouring School' --active admin
fi

if ! $COMPOSE users create --password alpha-user --schools 'Focus School Academy' alpha-user; then
  $COMPOSE users update --password alpha-user --schools 'Focus School Academy' --active alpha-user
fi

# Seed ODK Central with the minimal PHQ-9 fixture so the dimensions/variables
# endpoint has something to return. Fixed test credentials - this is a
# throwaway local ODK Central, not a real secret.
ODK_ADMIN_EMAIL="${ODK_ADMIN_EMAIL:-smoke-admin@glow.local}"
ODK_ADMIN_PASSWORD="${ODK_ADMIN_PASSWORD:-SmokeTest123!}"
ODK_API_EMAIL="${ODK_API_EMAIL:-smoke-api@glow.local}"
ODK_API_PASSWORD="${ODK_API_PASSWORD:-SmokeTest123!}"

if ! echo "$ODK_ADMIN_PASSWORD" | docker compose -f compose.yml -f compose.test.yml exec -T odk-service \
  node /usr/odk/lib/bin/cli.js -u "$ODK_ADMIN_EMAIL" user-create; then
  echo "$ODK_ADMIN_PASSWORD" | docker compose -f compose.yml -f compose.test.yml exec -T odk-service \
    node /usr/odk/lib/bin/cli.js -u "$ODK_ADMIN_EMAIL" user-set-password
fi
docker compose -f compose.yml -f compose.test.yml exec -T odk-service \
  node /usr/odk/lib/bin/cli.js -u "$ODK_ADMIN_EMAIL" user-promote || true

# odk-api-helper.sh's odk_curl never passes -k, so plain curl fails TLS
# verification against nginx's self-signed cert. Shim curl on PATH the same
# way dev-init.sh does.
ODK_CURL_WRAPPER_DIR=$(mktemp -d)
cat > "$ODK_CURL_WRAPPER_DIR/curl" <<'CURL_EOF'
#!/bin/bash
exec /usr/bin/curl -k -H "Host: odk.local" "$@"
CURL_EOF
chmod +x "$ODK_CURL_WRAPPER_DIR/curl"
export PATH="$ODK_CURL_WRAPPER_DIR:$PATH"

ODK_API_BASE="https://127.0.0.1:8443/v1"
ODK_DOMAIN="odk.local"
source scripts/odk/odk-api-helper.sh

ADMIN_TOKEN=$(odk_login "$ODK_ADMIN_EMAIL" "$ODK_ADMIN_PASSWORD")
PROJECT_ID=$(odk_create_project "GLOW Smoke Test" "$ADMIN_TOKEN")
API_ACTOR_ID=$(odk_create_user "$ODK_API_EMAIL" "$ODK_API_PASSWORD" "$ADMIN_TOKEN")
odk_assign_role "$PROJECT_ID" "$API_ACTOR_ID" "1" "$ADMIN_TOKEN" # 1 = Manager
odk_upload_form "$PROJECT_ID" "$(cat odk-forms/phq9_questionnaire.xml)" "$ADMIN_TOKEN"

python3 scripts/odk/seed_smoke_data.py \
  --csv testdata/demo_data.csv \
  --odk-url https://127.0.0.1:8443 \
  --project-id "$PROJECT_ID" \
  --email "$ODK_API_EMAIL" \
  --password "$ODK_API_PASSWORD"

# compose.yml's default GLOW_ODK_API_URL (http://odk-service:8383, internal
# plain HTTP) is rejected by ODK Central for Basic Auth ("This authentication
# method is only available over HTTPS", 401.3) - must go through nginx's TLS
# termination instead, same as dev's .env does for local dev.
export GLOW_ODK_API_URL="https://nginx"
export GLOW_ODK_VERIFY_SSL="false"
export GLOW_ODK_API_EMAIL="$ODK_API_EMAIL"
export GLOW_ODK_API_PASSWORD="$ODK_API_PASSWORD"
export GLOW_ODK_PROJECT_ID="$PROJECT_ID"
docker compose -f compose.yml -f compose.test.yml up -d --wait api dashboard

# api's /health is liveness-only and doesn't reflect DataStore's background
# initial ODK fetch (data.py DataStore.startup() loads async in a daemon
# thread; ODK Central's OData submissions endpoint can be slow to
# materialize for a freshly-created form/project). Poll /dimensions instead
# of trusting the healthcheck for data readiness.
echo "Waiting for /dimensions to reflect seeded ODK data..."
for i in $(seq 1 60); do
  VARS=$(curl -s http://127.0.0.1:8000/dimensions | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('variables', [])))" 2>/dev/null || echo 0)
  if [ "$VARS" -gt 0 ] 2>/dev/null; then
    echo "/dimensions ready ($VARS variables) after ${i}s"
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "Timed out waiting for /dimensions to report seeded variables" >&2
    echo "--- api logs ---" >&2
    docker compose -f compose.yml -f compose.test.yml logs api >&2
    exit 1
  fi
  sleep 1
done

python3 - <<'PY'
import json
import urllib.parse
import urllib.request

base = "http://127.0.0.1:8000"
login_req = urllib.request.Request(
    base + "/auth/login",
    data=urllib.parse.urlencode({"username": "admin", "password": "admin"}).encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    method="POST",
)
with urllib.request.urlopen(login_req) as response:
    token = json.loads(response.read().decode())["access_token"]

schools_req = urllib.request.Request(
    base + "/schools",
    headers={"Authorization": f"Bearer {token}"},
    method="GET",
)
with urllib.request.urlopen(schools_req) as response:
    print(response.read().decode())
PY

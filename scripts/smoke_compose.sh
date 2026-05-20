#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

cp testdata/demo_data.csv data/data.csv
rm -f data/auth.db data/auth.db-shm data/auth.db-wal

export GLOW_SECRET_KEY="${GLOW_SECRET_KEY:-smoke-test-secret}"

# Use canonical compose.yml + test overrides
docker compose -f compose.yml -f compose.test.yml down -v --remove-orphans
docker compose -f compose.yml -f compose.test.yml up --build -d --wait

# Healthcheck now guarantees API is ready, so seed users immediately
docker compose -f compose.yml -f compose.test.yml exec -T api glow-api users create --admin --password admin admin
docker compose -f compose.yml -f compose.test.yml exec -T api glow-api users create \
  --password alpha-user \
  --scope '{"filters":{"school":["Focus School Academy"]}}' \
  alpha-user

python3 - <<'PY'
import json
import urllib.parse
import urllib.request

base = "http://127.0.0.1:5173/api"
login_req = urllib.request.Request(
    base + "/auth/login",
    data=urllib.parse.urlencode({"username": "admin", "password": "admin"}).encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    method="POST",
)
with urllib.request.urlopen(login_req) as response:
    token = json.loads(response.read().decode())["access_token"]

query_req = urllib.request.Request(
    base + "/query",
    data=json.dumps({
        "steps": [
            {
                "type": "aggregate",
                "group_by": ["school"],
                "metrics": [{"kind": "count_students"}],
            }
        ]
    }).encode(),
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
    method="POST",
)
with urllib.request.urlopen(query_req) as response:
    print(response.read().decode())
PY

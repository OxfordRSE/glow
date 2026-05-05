#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

cp testdata/demo_data.csv data/data.csv
rm -f data/auth.db data/auth.db-shm data/auth.db-wal

export IB_OX_SECRET_KEY="${IB_OX_SECRET_KEY:-smoke-test-secret}"

docker compose up --build -d

python3 - <<'PY'
import time
import urllib.request

url = "http://127.0.0.1:5173/api/health"
deadline = time.time() + 60
last_error = None

while time.time() < deadline:
    try:
        with urllib.request.urlopen(url) as response:
            if response.status == 200:
                print(response.read().decode())
                break
    except Exception as exc:  # pragma: no cover - smoke script only
        last_error = exc
        time.sleep(1)
else:  # pragma: no cover - smoke script only
    raise SystemExit(f"Timed out waiting for {url}: {last_error}")
PY

docker compose exec -T api ib-ox-api users create --admin --password admin admin
docker compose exec -T api ib-ox-api users create \
  --password alpha-user \
  --scope '{"filters":{"school":["Alpha"]}}' \
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
    base + "/query/frequency",
    data=json.dumps({"group_by": ["school"], "filters": []}).encode(),
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
    method="POST",
)
with urllib.request.urlopen(query_req) as response:
    print(response.read().decode())
PY

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && { set -a; source .env; set +a; }
BASE="${MPT_BASE_URL:-http://localhost:8080}"
echo "Checking $BASE/docs"
curl -fsS -o /dev/null -w "HTTP %{http_code}\n" "$BASE/docs"
echo "Checking tasks endpoint"
curl -fsS "$BASE/api/v1/tasks?page=1&page_size=1" | python3 -m json.tool

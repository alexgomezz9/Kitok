#!/usr/bin/env bash
set -euo pipefail
HOST="$(ip route | awk '/default/ {print $3; exit}')"
echo "Probable Windows host from WSL: $HOST"
echo "Try: curl http://$HOST:8080/docs"
echo "If it works, set MPT_BASE_URL=http://$HOST:8080 in .env"

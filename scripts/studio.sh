#!/usr/bin/env bash
# One local server for the guided frontend and the Python API.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" != "" && "${1:-}" != "--check" ]]; then
  echo 'Uso: ./scripts/studio.sh [--check]' >&2
  exit 2
fi
if [[ ! -x .venv/bin/python ]]; then
  echo 'Falta el entorno Python. Ejecuta: make studio-setup' >&2
  exit 1
fi
# Use the existing project-local Node when the shell has no compatible version.
if ! command -v node >/dev/null || ! node -e 'const [m,n]=process.versions.node.split(".").map(Number);process.exit(m>22||(m===22&&n>=12)||(m===20&&n>=19)?0:1)' 2>/dev/null; then
  if [[ -x .tools/node/bin/node ]]; then
    export PATH="$PWD/.tools/node/bin:$PATH"
  else
    echo 'Instala Node 22.12+ o 24 y vuelve a ejecutar make studio-setup.' >&2
    exit 1
  fi
fi
if ! command -v npm >/dev/null; then
  echo 'Falta npm. Instálalo junto a Node y ejecuta make studio-setup.' >&2
  exit 1
fi
if [[ ! -d frontend/node_modules ]]; then
  echo 'Faltan las dependencias del frontend. Ejecuta: make studio-setup' >&2
  exit 1
fi
.venv/bin/python -c 'import kitok.api, uvicorn' || {
  echo 'Faltan dependencias Python. Ejecuta: make studio-setup' >&2
  exit 1
}
for binary in ffmpeg ffprobe; do
  if ! command -v "$binary" >/dev/null; then
    echo "Falta $binary. En Ubuntu/WSL: sudo apt install ffmpeg" >&2
    exit 1
  fi
done
if [[ "${1:-}" == '--check' ]]; then
  echo 'Python, API, Node, npm, dependencias frontend y FFmpeg disponibles.'
  echo 'Esta comprobación es local; no verifica credenciales ni servicios externos.'
  exit 0
fi
npm --prefix frontend run build
printf '\nAbre el estudio en http://127.0.0.1:8000\nMantén esta terminal abierta mientras se genera un vídeo.\n\n'
exec .venv/bin/python -m kitok.api

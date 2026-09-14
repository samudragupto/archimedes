#!/usr/bin/env bash
# =============================================================================
# ARCHIMEDES · scripts/setup.sh — one-shot developer setup (idempotent)
#
#   ./scripts/setup.sh          # from the repo root (or it cd's there itself)
#
# Does what `make setup` does, with friendlier errors:
#   1. checks python3 / pnpm
#   2. creates services/api/.venv + installs python deps (+ dev tools)
#   3. pnpm install for apps/web
#   4. copies .env.example → .env if missing
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "→ repo root: $ROOT"

command -v python3 >/dev/null || { echo "[!] python3 not found (need 3.11+)"; exit 1; }
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "→ python $PYVER"

if ! command -v pnpm >/dev/null; then
  echo "⚠ pnpm not found — attempting: npm install -g pnpm (skip with ctrl-c if you don't need the web app)"
  command -v npm >/dev/null && npm install -g pnpm || echo "[!] could not install pnpm; install it manually"
fi

VENV="$ROOT/services/api/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "→ creating python venv at services/api/.venv"
  python3 -m venv "$VENV"
fi
echo "→ installing python dependencies"
"$VENV/bin/pip" install --upgrade pip --quiet
"$VENV/bin/pip" install -r "$ROOT/services/api/requirements.txt" \
                        -r "$ROOT/services/api/requirements-dev.txt" --quiet

if command -v pnpm >/dev/null; then
  echo "→ installing web dependencies (pnpm)"
  pnpm --dir "$ROOT/apps/web" install
fi

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "→ created .env — now add your Nebius / Tavily / Supabase keys"
fi

cat <<'EOF'

==> Setup complete. Next steps:
   1. edit .env (Nebius, Tavily, Supabase keys — or set MOCK_LLM=true)
   2. apply supabase/migrations/0001_init.sql in your Supabase SQL editor
   3. make dev        (docker)   or   make api + make worker + make web
   4. make demo       (offline pipeline demo in your terminal)
   5. make test       (offline test suite)

EOF

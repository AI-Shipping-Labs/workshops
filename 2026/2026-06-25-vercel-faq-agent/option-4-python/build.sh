#!/usr/bin/env bash
# Build the single deployable Python service: a static Next.js frontend bundled
# into the FastAPI backend, which serves both the UI and the agent API.
#
# Run from option-4-python/. Used both locally (to preview the prod layout) and
# as the Vercel build command.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Building frontend (static export)"
cd frontend
npm ci
npm run build              # output: "export" → frontend/out
cd ..

echo "==> Copying frontend build into backend/static"
rm -rf backend/static
cp -r frontend/out backend/static

echo "==> Exporting requirements.txt from uv (Vercel's Python builder reads this)"
# Written to the option-4-python/ root, where @vercel/python looks for it.
( cd backend && uv export --frozen --no-dev --no-hashes --no-emit-project -o ../requirements.txt )

echo "==> Done. backend/ now serves the UI at / and the API at /chat, /search, /health."

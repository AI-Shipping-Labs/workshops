# --- Stage 1: build frontend ---
FROM node:24-alpine AS frontend-builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend ---
FROM public.ecr.aws/lambda/python:3.14

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR ${LAMBDA_TASK_ROOT}

COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --format requirements-txt | uv pip install --system -r -

ENV PYTHONUNBUFFERED=1

COPY backend/ ./backend/
COPY deploy/bootstrap ./bootstrap
RUN chmod +x ${LAMBDA_TASK_ROOT}/bootstrap
COPY --from=frontend-builder /app/dist ./static

ENTRYPOINT ["/var/task/bootstrap"]

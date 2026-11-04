.PHONY: install run dev frontend-install frontend docker-build docker-run langfuse-secrets stack-up stack-down stack-logs stack-ps

install:
	uv sync

run:
	uv run uvicorn app:app

dev:
	uv run uvicorn app:app --reload

frontend-install:
	cd frontend && npm install

frontend:
	cd frontend && npm run dev

docker-build:
	docker build -t faq-agent .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env faq-agent

# Generate secrets for self-hosted Langfuse and print export lines for .env
langfuse-secrets:
	@echo "ENCRYPTION_KEY=$$(openssl rand -hex 32)"
	@echo "NEXTAUTH_SECRET=$$(openssl rand -base64 32)"
	@echo "SALT=$$(openssl rand -base64 24 | tr -d '\n')"
	@echo "POSTGRES_PASSWORD=$$(openssl rand -base64 24 | tr -d '\n/+=')"
	@echo "CLICKHOUSE_PASSWORD=$$(openssl rand -base64 24 | tr -d '\n/+=')"
	@echo "MINIO_ROOT_PASSWORD=$$(openssl rand -base64 24 | tr -d '\n/+=')"
	@echo "REDIS_AUTH=$$(openssl rand -base64 24 | tr -d '\n/+=')"

# Full stack: Langfuse (UI :3000) + faq-agent (:8000)
stack-up:
	docker compose up --build -d
	docker compose ps

stack-down:
	docker compose down

stack-logs:
	docker compose logs -f langfuse-web faq-agent

stack-ps:
	docker compose ps

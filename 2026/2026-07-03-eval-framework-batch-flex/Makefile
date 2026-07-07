.PHONY: install run dev frontend-install frontend docker-build docker-run

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

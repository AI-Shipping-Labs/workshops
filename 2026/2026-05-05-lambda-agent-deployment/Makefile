.PHONY: install local dev backend lambda-local frontend-install frontend docker-build lambda-ecr-create lambda-push lambda-deploy lambda-url

install:
	uv sync

local: dev

dev:
	scripts/dev.sh

backend:
	uv run python scripts/dev-server.py

lambda-local:
	deploy/scripts/local-container.sh

frontend-install:
	cd frontend && npm install

frontend:
	cd frontend && npm run dev

docker-build:
	deploy/scripts/build-image.sh

lambda-ecr-create:
	deploy/scripts/create-ecr.sh

lambda-push:
	deploy/scripts/push-image.sh

lambda-deploy:
	deploy/scripts/deploy-lambda.sh

lambda-url:
	deploy/scripts/lambda-url.sh

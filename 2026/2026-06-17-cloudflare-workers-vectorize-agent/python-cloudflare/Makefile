PYTHON ?= python
PORT ?= 8792
WORKER_NAME ?= cloudflare-ai-agent-python

.PHONY: dev deploy delete

dev:
	$(PYTHON) scripts/with_root_env.py -- uv run pywrangler dev --port $(PORT)

deploy:
	$(PYTHON) scripts/with_root_env.py -- uv run pywrangler deploy

delete:
	$(PYTHON) scripts/with_root_env.py -- uv run pywrangler delete $(WORKER_NAME)

#!/usr/bin/env bash
set -euo pipefail

IMAGE_TAG="${IMAGE_TAG:-latest}"
ECR_REPOSITORY="${ECR_REPOSITORY:-faq-agent}"
PORT="${PORT:-9000}"

deploy/scripts/build-image.sh

docker run --rm \
  -p "${PORT}:8080" \
  --env-file .env \
  --entrypoint /usr/local/bin/aws-lambda-rie \
  "${ECR_REPOSITORY}:${IMAGE_TAG}" \
  /var/task/bootstrap

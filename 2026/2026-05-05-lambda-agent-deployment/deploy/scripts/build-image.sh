#!/usr/bin/env bash
set -euo pipefail

IMAGE_TAG="${IMAGE_TAG:-latest}"
ECR_REPOSITORY="${ECR_REPOSITORY:-faq-agent}"

docker build \
  --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  -t "${ECR_REPOSITORY}:${IMAGE_TAG}" \
  .

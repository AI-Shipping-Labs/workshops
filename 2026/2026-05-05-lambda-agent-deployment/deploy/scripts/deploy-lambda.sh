#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${STACK_NAME:-faq-agent-lambda}"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is required" >&2
  exit 1
fi

IMAGE_URI="${IMAGE_URI:-$(deploy/scripts/push-image.sh | tail -n 1)}"

aws cloudformation deploy \
  --template-file deploy/template.yaml \
  --stack-name "${STACK_NAME}" \
  --capabilities CAPABILITY_IAM \
  --region "${AWS_REGION}" \
  --parameter-overrides ImageUri="${IMAGE_URI}" OpenAIApiKey="${OPENAI_API_KEY}"

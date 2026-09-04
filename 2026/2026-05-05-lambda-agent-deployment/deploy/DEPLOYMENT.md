# Lambda Deployment Notes

This project deploys one Lambda container image that serves both the frontend and
the agent API through a Lambda Function URL.

## Final Architecture

The deployed image follows this architecture:

- The frontend is built with Vite during the Docker build.
- The built frontend files are copied into `/var/task/static`.
- `backend/lambda_runtime.py` handles Function URL requests directly:
  - `GET /` serves `static/index.html`
  - `GET /assets/...` serves frontend assets
  - `GET /health` returns a JSON health check
  - `POST /ask` returns a buffered JSON answer
  - `POST /ask/stream` returns Server-Sent Events
- The image uses the official AWS Lambda Python base image:
  - `public.ecr.aws/lambda/python:3.14`
- Python dependencies are installed into the Lambda system Python with `uv`.
- Deployment is done with `./deploy.sh`, which delegates work to `deploy/scripts/`.

## Custom Runtime

The normal Python Lambda handler style:

```dockerfile
CMD ["lambda_function.lambda_handler"]
```

is good for normal buffered responses, but it doesn't expose a streaming response
object for Python.

We need streaming for `/ask/stream`, so we use a custom runtime entrypoint:

```dockerfile
ENTRYPOINT ["/var/task/bootstrap"]
```

`bootstrap` runs `backend/lambda_runtime.py`, which talks to the Lambda Runtime API
directly and posts responses with:

```text
Lambda-Runtime-Function-Response-Mode: streaming
Transfer-Encoding: chunked
Content-Type: application/vnd.awslambda.http-integration-response
```

That's what allows the Lambda Function URL to stream SSE chunks to the browser.

## Deployment Command

Prerequisites:

- Docker is running.
- AWS CLI is configured.
- `.env` contains `OPENAI_API_KEY` and optionally `AWS_REGION`.

Deploy:

```bash
set -a
. ./.env
set +a
./deploy.sh
```

The script prints the Function URL at the end, which you can open in the browser.

## Useful Environment Variables

These can be exported before running `./deploy.sh`:

```bash
export AWS_REGION=eu-west-1
export STACK_NAME=faq-agent-lambda
export ECR_REPOSITORY=faq-agent
export IMAGE_TAG=$(date +%Y%m%d%H%M%S)
```

Use a unique `IMAGE_TAG` when redeploying changed image contents because
CloudFormation only sees the image URI string. If the URI stays `:latest`, it can
report "No changes to deploy" even when ECR has a newer image behind that tag.

## Local Testing

For normal day-to-day development without Docker:

```bash
export OPENAI_API_KEY=sk-...
make dev
```

Open `http://127.0.0.1:5173` to use the Vite frontend, which proxies API/SSE
requests to the local Python backend on port `8000`.

Run the exact production image through AWS Lambda Runtime Interface Emulator:

```bash
make lambda-local
```

Then invoke it from another shell:

```bash
curl -i http://127.0.0.1:9000/2015-03-31/functions/function/invocations \
  -d @events/health.json
```

Important: RIE doesn't emulate a public Function URL web server, so
`http://localhost:9000/` returns 404.

RIE accepts Lambda invoke requests only at this path:

```text
/2015-03-31/functions/function/invocations
```

For streaming responses, RIE returns the raw Lambda streaming integration
payload: response metadata, eight null bytes, then the body. In AWS, the
Function URL unwraps that into normal HTTP for the browser.

## Lambda Rejected The Docker Image Manifest

The first CloudFormation deploy failed with:

```text
The image manifest, config or layer media type for the source image ... is not supported.
```

Docker BuildKit produced an image manifest with provenance/SBOM attestation
metadata that Lambda rejected.

The build script now disables those settings:

```bash
docker build \
  --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  -t "${ECR_REPOSITORY}:${IMAGE_TAG}" \
  .
```

## Rolled Back Stack Had To Be Deleted

After the failed initial create, the stack ended in `ROLLBACK_COMPLETE`, and
CloudFormation can't update a stack in that state.

Delete it before redeploying:

```bash
aws cloudformation delete-stack \
  --stack-name faq-agent-lambda \
  --region "$AWS_REGION"

aws cloudformation wait stack-delete-complete \
  --stack-name faq-agent-lambda \
  --region "$AWS_REGION"
```

## Static Requests Were Slow On Cold Start

Originally, the runtime initialized the FAQ search index on cold start. That made
even `GET /` and `GET /health` wait for the FAQ download and index build.

To avoid that delay, `backend/search.py` now initializes the index lazily on the
first actual search. This keeps static frontend and health requests fast.

## Quick Verification After Deploy

Replace `FUNCTION_URL` with the printed URL:

```bash
curl -i "$FUNCTION_URL/health"
curl -i "$FUNCTION_URL/" | head -n 24
curl -N "$FUNCTION_URL/ask/stream" \
  -H 'content-type: application/json' \
  -d '{"question":"When is the course deadline?"}'
```

Expected:

- `/health` returns `{"status":"ok"}`.
- `/` returns the frontend HTML.
- `/ask/stream` returns `text/event-stream` chunks.

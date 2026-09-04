# Command Notes

Use these workshop command snippets as a quick reference, and replace
placeholder values before you run the commands.

## Prepare Cache Directories

Use `/workspace` on RunPod so model downloads and compiler caches survive pod
restarts and don't fill the container root filesystem.

```bash
mkdir -p /workspace/tmp \
  /workspace/hf-cache \
  /workspace/uv-cache \
  /workspace/vllm-cache \
  /workspace/triton-cache \
  /workspace/torchinductor-cache

export TMPDIR=/workspace/tmp
export TEMP=/workspace/tmp
export TMP=/workspace/tmp

export HF_HOME=/workspace/hf-cache
export HUGGINGFACE_HUB_CACHE=/workspace/hf-cache/hub
export UV_CACHE_DIR=/workspace/uv-cache
export VLLM_CACHE_ROOT=/workspace/vllm-cache

export TRITON_CACHE_DIR=/workspace/triton-cache
export TORCHINDUCTOR_CACHE_DIR=/workspace/torchinductor-cache
```

## Create A vLLM API Key

Generate a local bearer token for the vLLM API and keep it private.

```bash
export VLLM_API_KEY="$(openssl rand -hex 32)"
echo "VLLM_API_KEY=${VLLM_API_KEY}"
```

## Start vLLM On Port 8000

Use this for normal RunPod HTTP proxy access:
`https://<pod-id>-8000.proxy.runpod.net/v1`.

```bash
uv run vllm serve stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --host 0.0.0.0 \
  --port 8000 \
  --api-key "${VLLM_API_KEY}"
```

## Start vLLM On Port 8888

Use this only if the pod exposes HTTP port `8888` instead of `8000`.

```bash
uv run vllm serve stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --host 0.0.0.0 \
  --port 8888 \
  --api-key "${VLLM_API_KEY}"
```

## Start vLLM Without API Auth

Start vLLM without API authentication only for private debugging. Don't expose
an unauthenticated vLLM endpoint to the public internet.

```bash
uv run vllm serve stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90
```

## Smoke-Test The Endpoint

Run this from your laptop after setting `VLLM_BASE_URL` and `VLLM_API_KEY`.

```bash
export VLLM_BASE_URL="https://<pod-id>-8000.proxy.runpod.net/v1"
export VLLM_API_KEY="<your-vllm-api-key>"

uv run python src/check_vllm_gpu.py \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ
```

## Run The FAQ Agent

Force tool use for this model because auto mode is less reliable.

```bash
uv run python src/vllm_tool_agent.py \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --tool-choice search \
  --max-tokens 1024 \
  "How do I join the course?"
```

## RunPod HTTP Port Exposure

If creating a pod manually in the RunPod UI, expose the same internal HTTP port
that vLLM listens on.

1. Open the pod page.
2. Stop the pod if RunPod requires it for editing.
3. Edit the pod.
4. Find Expose HTTP Ports.
5. Add `8000`.
6. Save and restart the pod.

After the Pod restarts, use this public URL:

```text
https://<pod-id>-8000.proxy.runpod.net/v1
```

Test it:

```bash
curl "https://<pod-id>-8000.proxy.runpod.net/v1/models" \
  -H "Authorization: Bearer <your-vllm-api-key>"
```

RunPod's HTTP proxy can time out on long non-streaming generations, so streaming
is useful for longer responses. Keep `--host 0.0.0.0 --port 8000` in the vLLM
command.

See [Expose HTTP ports](https://docs.runpod.io/pods/configuration/expose-ports)
in the RunPod documentation.

## OpenAI Client Example

Use the RunPod proxy URL as the OpenAI-compatible base URL.

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://<pod-id>-8000.proxy.runpod.net/v1",
    api_key="<your-vllm-api-key>",
)
```

## Codex Session Logs

Codex session logs are stored under:

```text
~/.codex/sessions/YYYY/MM/DD/
```

For this workshop, local June 2, 2026 session logs were copied into:

```text
.codex/sessions/2026/06/02/
```

Don't publish `.codex` logs without checking for secrets first.

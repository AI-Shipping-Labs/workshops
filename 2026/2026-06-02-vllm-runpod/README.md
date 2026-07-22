# Serving Open-Source Models with vLLM and RunPod

[Follow the tutorial on AI Shipping Labs](https://aishippinglabs.com/workshops/serving-open-models-vllm-runpod).

This workshop shows how to serve an open-source model with vLLM on RunPod,
expose it through vLLM's OpenAI-compatible API, verify GPU access inside the
container, and run a small FAQ agent against the deployed endpoint.

The tested model is `stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ`. The model
weights are not baked into an image; vLLM downloads them at pod startup and
caches them under `/workspace/hf-cache/hub`.

## Project Structure

```text
.
├── README.md
├── pyproject.toml
├── uv.lock
├── deploy/
│   └── runpod/
│       ├── create-pod.ps1
│       └── runpod.env.example
├── docs/
│   ├── commands.md
│   ├── copy-from-runpod.md
│   └── setup.md
├── scripts/
│   └── check-remote-nvidia-smi.py
└── src/
    ├── check_vllm_gpu.py
    └── vllm_tool_agent.py
```

- `src/check_vllm_gpu.py`: smoke-tests a vLLM OpenAI-compatible endpoint.
- `src/vllm_tool_agent.py`: runs the FAQ agent against vLLM.
- `deploy/runpod/`: RunPod deployment helper and environment example.
- `scripts/`: small operational utilities.
- `docs/`: setup notes and historical command snippets.

## Reproducible RunPod Deployment

Use the official `vllm/vllm-openai:latest` image directly and override the
startup command through the RunPod API or `runpodctl`. This avoids pushing a
derived 35GB image just to add a small startup script.

Get your RunPod API key:

1. Open the [RunPod Console](https://console.runpod.io/).
2. Go to Settings.
3. Expand API Keys, then click Create API Key.
4. Give it a name, choose permissions (All, Restricted, or Read Only), then click Create.
5. Click the newly created key to copy it.

RunPod does not store the key, so copy and save it right away. Treat it like a
password. Full guide: [Manage API keys](https://docs.runpod.io/get-started/api-keys).

Set local secrets:

```bash
export RUNPOD_API_KEY="..."
export VLLM_API_KEY="replace-with-a-long-random-secret"
```

Or put them in `.env`:

```text
RUNPOD_API_KEY=replace-with-your-runpod-api-key
VLLM_API_KEY=replace-with-a-long-random-secret
```

Install and configure `runpodctl`:

```bash
runpodctl doctor
runpodctl user
```

The working SSH-enabled template created for this setup is:

```text
Template name: vllm-deepseek-awq-api-ssh
Template ID: neh2kqf1zt
```

Create a Pod from the template:

```bash
stop_after="$(date -u -d '+4 hours' '+%Y-%m-%dT%H:%M:%SZ')"
pod_env="{\"VLLM_API_KEY\":\"${VLLM_API_KEY}\"}"

runpodctl pod create \
  --template-id neh2kqf1zt \
  --name vllm-deepseek-awq-ssh \
  --cloud-type COMMUNITY \
  --gpu-id "NVIDIA RTX PRO 6000 Blackwell Server Edition" \
  --gpu-count 1 \
  --volume-in-gb 40 \
  --public-ip \
  --env "$pod_env" \
  --stop-after "$stop_after"
```

Why `--public-ip`: RunPod SSH needs an external TCP mapping for port `22`.
Without it, `runpodctl ssh info <pod-id>` can report `pod not ready` even when
the vLLM HTTP API is already serving.

The template configures:

- Container image: `vllm/vllm-openai:latest`
- Exposed HTTP port: `8000`
- Exposed SSH port: `22/tcp`
- Persistent volume mount: `/workspace`, so model caches survive Pod restarts
- Cloud type: `COMMUNITY`
- GPU used successfully: RTX PRO 6000 Blackwell Server Edition
- Startup command starts `sshd`, then starts `vllm serve`

RunPod REST pod creation accepts `cloudType` values `SECURE` or `COMMUNITY`;
`ALL` is not valid for the REST endpoint. For Europe/Czech deployments, use
datacenter `EU-CZ-1`. At the time of checking, `EU-CZ-1` listed RTX 3090,
RTX 4090, RTX 5090, and RTX PRO 6000 availability.

Template environment variables:

```text
MODEL_ID=stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ
PORT=8000
MAX_MODEL_LEN=8192
GPU_MEMORY_UTILIZATION=0.90
ENABLE_AUTO_TOOL_CHOICE=true
TOOL_CALL_PARSER=hermes
VLLM_API_KEY=replace-with-a-long-random-secret
```

Optional:

```text
HF_TOKEN=hf_...
EXTRA_VLLM_ARGS=--cpu-offload-gb 8
```

The model weights are not included in the Docker image. vLLM downloads them on
first startup and caches them in `/workspace/hf-cache/hub`.

After the Pod starts, set the OpenAI-compatible base URL:

```text
https://<pod-id>-8000.proxy.runpod.net/v1
```

For example, the tested pod was:

```text
POD_ID=<pod-id>
VLLM_BASE_URL=https://<pod-id>-8000.proxy.runpod.net/v1
```

Test it:

```bash
curl "https://<pod-id>-8000.proxy.runpod.net/v1/models" \
  -H "Authorization: Bearer $VLLM_API_KEY"
```

For local scripts, put `VLLM_API_KEY` and `VLLM_BASE_URL` in `.env`, then load:

```bash
set -a
source .env
set +a
```

Run the repo smoke test:

```bash
uv run python src/check_vllm_gpu.py \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --prompt "In one sentence, say that vLLM is running." \
  --max-tokens 96
```

Run the FAQ agent. For this model, forced tool mode is more reliable than
automatic tool choice:

```bash
uv run python src/vllm_tool_agent.py \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --tool-choice search \
  --max-tokens 1024 \
  "How do I join the course?"
```

Connect with SSH:

```bash
runpodctl ssh info <pod-id>
```

Use the returned command, for example:

```bash
ssh -i "$HOME/.runpod/ssh/runpodctl-ssh-key" root@<public-ip> -p <ssh-port>
```

Check the GPU inside the container:

```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu \
  --format=csv,noheader,nounits
```

The tested pod returned:

```text
0, NVIDIA RTX PRO 6000 Blackwell Server Edition, 10577, 97887, 0
```

Stop the Pod when done:

```bash
runpodctl pod stop <pod-id>
runpodctl pod list
```

Stopping is important: GPU Pods bill by the hour while running. `pod list`
should return `[]` or show no `RUNNING` Pod when you are finished. Use
`--stop-after` when creating Pods as a backup spend limit.

For a different model, change only `MODEL_ID` and any memory/context settings
in the template environment. For a gated model, set `HF_TOKEN`.

## Start vLLM

Use `/workspace` for caches and temporary files so model downloads and compiler
caches do not fill the container root filesystem.

```bash
mkdir -p /workspace/tmp /workspace/hf-cache /workspace/uv-cache \
  /workspace/vllm-cache /workspace/triton-cache /workspace/torchinductor-cache

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

For normal chat:

```bash
export VLLM_API_KEY="$(openssl rand -hex 32)"

uv run vllm serve stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --host 0.0.0.0 \
  --port 8000 \
  --api-key "$VLLM_API_KEY" \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90
```

For tool calling, restart vLLM with a tool parser:

```bash
export VLLM_API_KEY="$(openssl rand -hex 32)"

uv run vllm serve stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --host 0.0.0.0 \
  --port 8000 \
  --api-key "$VLLM_API_KEY" \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

## Access From Another Computer

Find this machine's LAN IP address:

```bash
hostname -I
```

Use the address that looks like `192.168.x.x`, `10.x.x.x`, or `172.16-31.x.x`.
From another computer on the same network, call vLLM with the same bearer token:

```bash
export VLLM_BASE_URL="http://SERVER_LAN_IP:8000"
export VLLM_API_KEY="the-secret-token-from-the-server"

curl "$VLLM_BASE_URL/v1/models" \
  -H "Authorization: Bearer $VLLM_API_KEY"
```

Chat request:

```bash
curl "$VLLM_BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $VLLM_API_KEY" \
  -d '{
    "model": "stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ",
    "messages": [{"role": "user", "content": "In one sentence, what is vLLM?"}],
    "max_tokens": 64
  }'
```

The Python test scripts also read `VLLM_BASE_URL` and `VLLM_API_KEY`, so they
can be run against the network endpoint:

```bash
uv run python src/check_vllm_gpu.py \
  --base-url "$VLLM_BASE_URL" \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ
```

Keep the token private. Do not put it in the repo, shell history, chat messages,
or screenshots. vLLM's `--api-key` protects the OpenAI-compatible API by
requiring `Authorization: Bearer <token>` on requests. For internet exposure,
put vLLM behind a VPN or HTTPS reverse proxy; do not expose raw port `8000` to
the public internet.

## Test GPU Usage

```bash
uv run python src/check_vllm_gpu.py \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ
```

For streaming tokens:

```bash
uv run python src/check_vllm_gpu.py \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --stream
```

## Test Tool Use

```bash
uv run python src/vllm_tool_agent.py \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  "How do I submit homework?"
```

Increase answer length if needed:

```bash
uv run python src/vllm_tool_agent.py \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --max-tokens 2048 \
  "How do I join the course?"
```

The agent uses `--tool-choice auto` by default. To force the search tool only
when debugging tool transport:

```bash
uv run python src/vllm_tool_agent.py \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --tool-choice search \
  "How do I submit homework?"
```

In auto mode, the script retries once with a stricter prompt if the model
answers without a tool call. Tune that with `--tool-retries`.

With this AWQ DeepSeek/Qwen model, vLLM may not return native `tool_calls` in
auto mode. The agent also accepts a model-written JSON tool call like:

```json
{"name":"search","arguments":{"query":"how do I join the course?"}}
```

That still produces the intended two-call loop: model requests search, Python
executes search, then Python sends the tool result back to the model.

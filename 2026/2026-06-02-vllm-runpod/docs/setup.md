# Reproducible RunPod vLLM Setup

## 1. Use The Official vLLM Image

Use `vllm/vllm-openai:latest` directly, and don't build or push a custom image
for this workshop.

## 2. Create A RunPod Pod Via API

Get your RunPod API key:

1. Open the [RunPod Console](https://console.runpod.io/).
2. Go to Settings.
3. Expand API Keys, then click Create API Key.
4. Give it a name, choose permissions (All, Restricted, or Read Only), then click Create.
5. Click the newly created key to copy it.

RunPod doesn't store the key, so copy and save it right away. Treat it like a
password. Full guide: [Manage API keys](https://docs.runpod.io/get-started/api-keys).

Set secrets locally:

```bash
export RUNPOD_API_KEY="..."
export VLLM_API_KEY="replace-with-a-long-random-secret"
```

Or put them in `.env`:

```text
RUNPOD_API_KEY=replace-with-your-runpod-api-key
VLLM_API_KEY=replace-with-a-long-random-secret
```

Optionally override defaults:

```bash
export MODEL_ID="stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ"
export MAX_MODEL_LEN="8192"
export GPU_MEMORY_UTILIZATION="0.90"
export EXTRA_VLLM_ARGS="--cpu-offload-gb 8"
```

Create the Pod:

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

Use this working template:

```text
Template name: vllm-deepseek-awq-api-ssh
Template ID: neh2kqf1zt
```

When you run the command, RunPod creates a GPU Pod with these settings:

```text
Container image: vllm/vllm-openai:latest
Expose HTTP ports: 8000
Expose SSH ports: 22/tcp
Network volume mount: /workspace
Cloud type: COMMUNITY
GPU used successfully: RTX PRO 6000 Blackwell Server Edition
Startup command: start sshd, then start vLLM
```

## 3. Environment Variables Used On The Pod

Set these environment variables on the Pod:

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

## 4. Runtime Behavior

Because the image doesn't contain the model, vLLM downloads `MODEL_ID` on first
startup and caches it under `/workspace/hf-cache/hub`. Reuse the same RunPod
volume to avoid downloading the model again.

After the Pod starts, the OpenAI-compatible base URL will be:

```text
https://<pod-id>-8000.proxy.runpod.net/v1
```

## 5. Test The API

List the models served by the API:

```bash
curl https://<pod-id>-8000.proxy.runpod.net/v1/models \
  -H "Authorization: Bearer $VLLM_API_KEY"
```

## 6. Configure Your Laptop

Export the API key and base URL on your laptop:

```bash
export VLLM_API_KEY=replace-with-a-long-random-secret
export VLLM_BASE_URL=https://<pod-id>-8000.proxy.runpod.net/v1
```

## 7. Run The Agent

Ask the FAQ agent a question:

```bash
python src/vllm_tool_agent.py "how do I join the course?"
```

For this model, forced tool mode is more reliable than automatic tool choice:

```bash
uv run python src/vllm_tool_agent.py \
  --model stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ \
  --tool-choice search \
  --max-tokens 1024 \
  "How do I join the course?"
```

## 8. SSH And GPU Check

Get the Pod's SSH connection details:

```bash
runpodctl ssh info <pod-id>
```

Use the returned SSH command, then check the GPU inside the container:

```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu \
  --format=csv,noheader,nounits
```

The tested pod returned:

```text
0, NVIDIA RTX PRO 6000 Blackwell Server Edition, 10577, 97887, 0
```

## 9. Stop The Pod

Stop the Pod when done:

```bash
runpodctl pod stop <pod-id>
runpodctl pod list
```

Stop the Pod because GPU Pods bill by the hour while running. `pod list`
should return `[]` or show no `RUNNING` Pod when you're finished. Use
`--stop-after` when creating Pods as a backup spend limit.

You don't need to configure SSH manually. The container starts vLLM
automatically, uses `/workspace` for model/cache/temp files, enables tool-call
support, and serves an OpenAI-compatible API.

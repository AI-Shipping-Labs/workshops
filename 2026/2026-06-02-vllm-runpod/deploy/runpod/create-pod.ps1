param(
  [string]$Name = "vllm-deepseek-awq",
  [string]$ImageName = "vllm/vllm-openai:latest",
  [string[]]$GpuTypeIds = @(
    "NVIDIA GeForce RTX 3090",
    "NVIDIA GeForce RTX 4090",
    "NVIDIA GeForce RTX 5090",
    "NVIDIA RTX PRO 6000 Blackwell Server Edition"
  ),
  [int]$GpuCount = 1,
  [int]$ContainerDiskInGb = 50,
  [int]$VolumeInGb = 100,
  [string]$VolumeMountPath = "/workspace",
  [string]$CloudType = "COMMUNITY",
  [string[]]$DataCenterIds = @("EU-CZ-1", "EU-RO-1", "EU-SE-1", "EUR-NO-1"),
  [switch]$Interruptible,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $env:RUNPOD_API_KEY) {
  throw "RUNPOD_API_KEY is required. Set it before running this script."
}

if (-not $env:VLLM_API_KEY) {
  throw "VLLM_API_KEY is required. Set it before running this script."
}

$modelId = if ($env:MODEL_ID) { $env:MODEL_ID } else { "stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ" }
$port = if ($env:PORT) { $env:PORT } else { "8000" }
$maxModelLen = if ($env:MAX_MODEL_LEN) { $env:MAX_MODEL_LEN } else { "8192" }
$gpuMemoryUtilization = if ($env:GPU_MEMORY_UTILIZATION) { $env:GPU_MEMORY_UTILIZATION } else { "0.90" }
$enableAutoToolChoice = if ($env:ENABLE_AUTO_TOOL_CHOICE) { $env:ENABLE_AUTO_TOOL_CHOICE } else { "true" }
$toolCallParser = if ($env:TOOL_CALL_PARSER) { $env:TOOL_CALL_PARSER } else { "hermes" }
$extraVllmArgs = if ($env:EXTRA_VLLM_ARGS) { $env:EXTRA_VLLM_ARGS } else { "" }

$startScript = @'
set -euo pipefail

mkdir -p \
  /workspace/tmp \
  /workspace/hf-cache \
  /workspace/vllm-cache \
  /workspace/triton-cache \
  /workspace/torchinductor-cache

export TMPDIR="${TMPDIR:-/workspace/tmp}"
export TEMP="${TEMP:-/workspace/tmp}"
export TMP="${TMP:-/workspace/tmp}"
export HF_HOME="${HF_HOME:-/workspace/hf-cache}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-/workspace/hf-cache/hub}"
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-/workspace/vllm-cache}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-/workspace/triton-cache}"
export TORCHINDUCTOR_CACHE_DIR="${TORCHINDUCTOR_CACHE_DIR:-/workspace/torchinductor-cache}"

args=(
  "vllm"
  "serve"
  "${MODEL_ID}"
  "--host" "0.0.0.0"
  "--port" "${PORT:-8000}"
  "--api-key" "${VLLM_API_KEY}"
  "--max-model-len" "${MAX_MODEL_LEN:-8192}"
  "--gpu-memory-utilization" "${GPU_MEMORY_UTILIZATION:-0.90}"
)

if [[ "${ENABLE_AUTO_TOOL_CHOICE:-true}" == "true" ]]; then
  args+=("--enable-auto-tool-choice")
  args+=("--tool-call-parser" "${TOOL_CALL_PARSER:-hermes}")
fi

echo "Starting vLLM on 0.0.0.0:${PORT:-8000}"
echo "Model: ${MODEL_ID}"
echo "Cache: ${HUGGINGFACE_HUB_CACHE}"

# shellcheck disable=SC2086
exec "${args[@]}" ${EXTRA_VLLM_ARGS:-}
'@

$envObject = [ordered]@{
  MODEL_ID = $modelId
  PORT = $port
  MAX_MODEL_LEN = $maxModelLen
  GPU_MEMORY_UTILIZATION = $gpuMemoryUtilization
  ENABLE_AUTO_TOOL_CHOICE = $enableAutoToolChoice
  TOOL_CALL_PARSER = $toolCallParser
  VLLM_API_KEY = $env:VLLM_API_KEY
}

if ($env:HF_TOKEN) {
  $envObject.HF_TOKEN = $env:HF_TOKEN
}

if ($extraVllmArgs) {
  $envObject.EXTRA_VLLM_ARGS = $extraVllmArgs
}

$body = [ordered]@{
  cloudType = $CloudType
  computeType = "GPU"
  imageName = $ImageName
  name = $Name
  gpuCount = $GpuCount
  gpuTypeIds = $GpuTypeIds
  gpuTypePriority = "availability"
  containerDiskInGb = $ContainerDiskInGb
  volumeInGb = $VolumeInGb
  volumeMountPath = $VolumeMountPath
  dataCenterIds = $DataCenterIds
  minRAMPerGPU = 24
  minVCPUPerGPU = 4
  ports = @("$port/http")
  dockerEntrypoint = @("bash", "-lc")
  dockerStartCmd = @($startScript)
  env = $envObject
  interruptible = [bool]$Interruptible
}

$json = $body | ConvertTo-Json -Depth 20

if ($DryRun) {
  $json
  exit 0
}

$response = Invoke-RestMethod `
  -Method Post `
  -Uri "https://rest.runpod.io/v1/pods" `
  -Headers @{
    Authorization = "Bearer $env:RUNPOD_API_KEY"
    "Content-Type" = "application/json"
  } `
  -Body $json

$response | ConvertTo-Json -Depth 20

if ($response.id) {
  Write-Host ""
  Write-Host "Pod ID: $($response.id)"
  Write-Host "Base URL: https://$($response.id)-$port.proxy.runpod.net/v1"
}

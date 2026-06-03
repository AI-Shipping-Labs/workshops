#!/usr/bin/env python3
"""Send a test request to a local vLLM server and print GPU usage."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator


DEFAULT_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B"
DEFAULT_API_KEY = os.environ.get("VLLM_API_KEY", "local-test")


def request_headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "curl/8.5.0",
    }


def normalize_base_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        return base_url[:-3]
    return base_url


def run_nvidia_smi() -> str | None:
    if shutil.which("nvidia-smi") is None:
        return None

    fields = [
        "index",
        "name",
        "memory.used",
        "memory.total",
        "utilization.gpu",
    ]
    cmd = [
        "nvidia-smi",
        f"--query-gpu={','.join(fields)}",
        "--format=csv,noheader,nounits",
    ]
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return exc.output.strip()


def post_json(url: str, payload: dict, timeout: float, api_key: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers(api_key),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def stream_chat_completion(
    url: str, payload: dict, timeout: float, api_key: str
) -> Iterator[dict]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers(api_key),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue

            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                break
            yield json.loads(data)


def get_json(url: str, timeout: float, api_key: str) -> dict:
    request = urllib.request.Request(
        url,
        headers=request_headers(api_key),
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def print_gpu_snapshot(label: str) -> None:
    print(f"\n[{label}] GPU snapshot")
    snapshot = run_nvidia_smi()
    if snapshot is None:
        print("nvidia-smi not found")
        return
    print("gpu, name, mem_used_mib, mem_total_mib, gpu_util_percent")
    print(snapshot or "No GPU rows returned")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check a local vLLM OpenAI-compatible server and GPU usage."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="Bearer token for a vLLM server started with --api-key.",
    )
    parser.add_argument(
        "--prompt",
        default="In one sentence, explain what vLLM is.",
    )
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream tokens from vLLM as they arrive.",
    )
    args = parser.parse_args()

    base_url = normalize_base_url(args.base_url)

    try:
        models = get_json(f"{base_url}/v1/models", timeout=10, api_key=args.api_key)
    except urllib.error.URLError as exc:
        print(f"Could not reach vLLM at {base_url}: {exc}", file=sys.stderr)
        print(
            "Start it first, for example:\n"
            f"  uv run vllm serve {args.model}",
            file=sys.stderr,
        )
        return 1

    served_models = [item.get("id") for item in models.get("data", [])]
    print(f"Connected to {base_url}")
    print(f"Served models: {', '.join(served_models) or '(none reported)'}")

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "max_tokens": args.max_tokens,
        "temperature": 0,
        "stream": args.stream,
    }

    print_gpu_snapshot("before request")
    started = time.time()

    print("\n[response]")
    usage = {}
    if args.stream:
        content_parts = []
        try:
            for chunk in stream_chat_completion(
                f"{base_url}/v1/chat/completions",
                payload,
                timeout=args.timeout,
                api_key=args.api_key,
            ):
                if chunk.get("usage"):
                    usage = chunk["usage"]

                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {})
                    token = delta.get("content") or ""
                    if token:
                        content_parts.append(token)
                        print(token, end="", flush=True)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(f"\nvLLM returned HTTP {exc.code}: {body}", file=sys.stderr)
            return 1
        except urllib.error.URLError as exc:
            print(f"\nRequest failed: {exc}", file=sys.stderr)
            return 1
        print()
    else:
        try:
            response = post_json(
                f"{base_url}/v1/chat/completions",
                payload,
                timeout=args.timeout,
                api_key=args.api_key,
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(f"vLLM returned HTTP {exc.code}: {body}", file=sys.stderr)
            return 1
        except urllib.error.URLError as exc:
            print(f"Request failed: {exc}", file=sys.stderr)
            return 1

        choice = response["choices"][0]
        usage = response.get("usage", {})
        content = choice.get("message", {}).get("content", "")
        print(content.strip())

    elapsed = time.time() - started
    print_gpu_snapshot("after request")
    print("\n[usage]")
    print(json.dumps(usage or "(not returned for streaming response)", indent=2))
    print(f"\nCompleted in {elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

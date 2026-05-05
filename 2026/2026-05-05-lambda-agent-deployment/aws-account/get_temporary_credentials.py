#!/usr/bin/env python3
"""Generate temporary AWS credentials for an existing experiments account."""


import argparse
import json
import pathlib
import shlex
import subprocess
import sys

import boto3

from config import env, load_experiments_config
from update_env_file import update_env_file

load_experiments_config()

ACCOUNT_ID = env("AWS_EXPERIMENTS_ACCOUNT_ID", "")
ROLE_NAME = env("AWS_EXPERIMENTS_ACCESS_ROLE_NAME", "OrganizationAccountAccessRole")
if not ACCOUNT_ID:
    raise SystemExit("AWS_EXPERIMENTS_ACCOUNT_ID is required in .env or the environment")
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"

REMOTE_UPDATE_SCRIPT = r"""
import json
import pathlib


def update_env_lines(existing_lines, updates):
    remaining = dict(updates)
    output = []

    for line in existing_lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue

        key = line.split("=", 1)[0].strip()
        if key in remaining:
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)

    if remaining and output and output[-1] != "":
        output.append("")
    for key, value in remaining.items():
        output.append(f"{key}={value}")

    return output


payload = json.load(__import__("sys").stdin)
path = pathlib.Path(payload["path"]).expanduser()
updates = payload["updates"]
existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("\n".join(update_env_lines(existing, updates)) + "\n", encoding="utf-8", newline="\n")
path.chmod(0o600)
"""

REMOTE_VERIFY_SCRIPT = r"""
import json
import pathlib

path = pathlib.Path(json.load(__import__("sys").stdin)["path"]).expanduser()
lines = path.read_text(encoding="utf-8").splitlines()
print(f"{len(lines)} {path}")
for line in lines:
    if line and not line.lstrip().startswith("#") and "=" in line:
        print(line.split("=", 1)[0].strip())
"""


def get_credentials(region: str, duration_seconds: int) -> tuple[dict[str, str], str]:
    sts = boto3.client("sts")
    response = sts.assume_role(
        RoleArn=ROLE_ARN,
        RoleSessionName="lambda-deploy-env-python-2h",
        DurationSeconds=duration_seconds,
    )
    creds = response["Credentials"]
    expiration = creds["Expiration"].isoformat()

    return (
        {
            "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
            "AWS_SESSION_TOKEN": creds["SessionToken"],
            "AWS_DEFAULT_REGION": region,
            "AWS_REGION": region,
            "AWS_ACCOUNT_ID": ACCOUNT_ID,
            "AWS_CREDENTIAL_EXPIRATION": expiration,
        },
        expiration,
    )


def update_remote_env_file(remote_host: str, remote_path: str, updates: dict[str, str]) -> None:
    payload = json.dumps({"path": remote_path, "updates": updates})
    command = f"python3 -c {shlex.quote(REMOTE_UPDATE_SCRIPT)}"
    subprocess.run(["ssh", remote_host, command], input=payload, text=True, check=True)


def verify_remote(remote_host: str, remote_path: str) -> None:
    payload = json.dumps({"path": remote_path})
    command = f"python3 -c {shlex.quote(REMOTE_VERIFY_SCRIPT)}"
    subprocess.run(["ssh", remote_host, command], input=payload, text=True, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="eu-west-1")
    parser.add_argument("--duration-seconds", type=int, default=7200)
    parser.add_argument("--output", default="experiments-env")
    parser.add_argument("--remote-host", default=None)
    parser.add_argument("--remote-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = pathlib.Path(args.output)
    updates, expiration = get_credentials(args.region, args.duration_seconds)
    update_env_file(output, updates)

    if args.remote_host:
        if not args.remote_path:
            raise SystemExit("--remote-path is required when --remote-host is set")
        update_remote_env_file(args.remote_host, args.remote_path, updates)
        verify_remote(args.remote_host, args.remote_path)

    print(f"Wrote {output}")
    print(f"Expires: {expiration}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

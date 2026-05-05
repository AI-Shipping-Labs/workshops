"""Configuration helpers for the AWS experiments scripts."""


import os
import pathlib


CONFIG_PATH = pathlib.Path(".env")


def load_experiments_config(path: pathlib.Path = CONFIG_PATH) -> None:
    """Load only AWS_EXPERIMENTS_* config keys from the local config file."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.startswith("AWS_EXPERIMENTS_"):
            continue
        os.environ.setdefault(key, value.strip().strip("'\""))


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)

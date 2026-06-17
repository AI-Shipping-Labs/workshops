import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Loads the repository root .env file, then runs the requested command."""

    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    load_env_file(env_path)

    args = sys.argv[1:]
    if args[:1] == ["--"]:
        args = args[1:]

    if not args:
        print("Usage: python scripts/with_root_env.py -- <command> [...args]", file=sys.stderr)
        return 1

    os.environ["ROOT_ENV_FILE"] = str(env_path)
    args = [str(env_path) if arg == "__ROOT_ENV_FILE__" else arg for arg in args]

    return subprocess.call(args)


def load_env_file(path: Path) -> None:
    """Loads KEY=VALUE lines from .env without overriding existing variables."""

    if not path.exists():
        print(f"Root .env not found at {path}", file=sys.stderr)
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = strip_quotes(value.strip())
        os.environ.setdefault(key, value)


def strip_quotes(value: str) -> str:
    """Removes one matching pair of shell-style quotes from an env value."""

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


if __name__ == "__main__":
    raise SystemExit(main())

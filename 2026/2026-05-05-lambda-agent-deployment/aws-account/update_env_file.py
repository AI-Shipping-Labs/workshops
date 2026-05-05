#!/usr/bin/env python3
"""Update or append variables in an env file while preserving unrelated lines."""


import argparse
import pathlib
import sys


def parse_assignment(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(f"Expected KEY=VALUE, got {value!r}")
    key, assignment_value = value.split("=", 1)
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError(f"Expected non-empty key in {value!r}")
    return key, assignment_value


def update_env_lines(existing_lines: list[str], updates: dict[str, str]) -> list[str]:
    remaining = dict(updates)
    output: list[str] = []

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


def update_env_file(path: pathlib.Path, updates: dict[str, str]) -> None:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated_lines = update_env_lines(existing_lines, updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(updated_lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("assignments", nargs="+", type=parse_assignment)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    update_env_file(pathlib.Path(args.path), dict(args.assignments))
    return 0


if __name__ == "__main__":
    sys.exit(main())

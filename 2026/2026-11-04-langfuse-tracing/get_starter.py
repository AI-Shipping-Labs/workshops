"""Download the previous FAQ workshop's starter files without cloning Git."""

import argparse
from pathlib import Path
from urllib.request import Request, urlopen


SOURCE_COMMIT = "e641e439946099c6389efabd1dde19292b1a9add"
SOURCE_DIRECTORY = "2026/2026-04-21-end-to-end-agent-deployment"
BASE_URL = (
    "https://raw.githubusercontent.com/AI-Shipping-Labs/workshops/"
    f"{SOURCE_COMMIT}/{SOURCE_DIRECTORY}"
)
FILES = (
    ".dockerignore",
    ".python-version",
    "Dockerfile",
    "Makefile",
    "README.md",
    "agent.py",
    "app.py",
    "pyproject.toml",
    "renderer.py",
    "schemas.py",
    "search.py",
    "uv.lock",
    "frontend/index.html",
    "frontend/main.js",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/style.css",
    "frontend/vite.config.js",
)


def download_starter(directory):
    destination = Path(directory).expanduser().resolve()
    targets = [(name, destination / name) for name in FILES]
    for name, target in targets:
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Won't replace an existing file: {target}")
        if not target.resolve().is_relative_to(destination):
            raise ValueError(f"File would leave the destination: {name}")
        for parent in target.parents:
            if parent.exists() and not parent.is_dir():
                raise NotADirectoryError(f"Expected a folder: {parent}")

    # Fetch only the listed starter files, before writing any of them.
    downloads = []
    for name, target in targets:
        request = Request(f"{BASE_URL}/{name}", headers={"User-Agent": "AISL-starter"})
        with urlopen(request, timeout=30) as response:
            downloads.append((target, response.read()))

    for target, data in downloads:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(data)
    print(f"Downloaded {len(downloads)} starter files into {destination}")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory", nargs="?", default=".",
        help="Folder for the starter files (default: current folder).",
    )
    arguments = parser.parse_args()
    download_starter(arguments.directory)


if __name__ == "__main__":
    main()

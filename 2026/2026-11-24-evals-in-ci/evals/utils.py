"""Small helpers shared across eval scripts."""

import asyncio
import json
from pathlib import Path

from tqdm.auto import tqdm


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


async def map_progress(seq, func, max_concurrency=5, desc=None):
    """Run `func` over `seq` concurrently (bounded) with a progress bar."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def run_with_semaphore(item):
        async with semaphore:
            return await func(item)

    coros = [run_with_semaphore(el) for el in seq]
    results = []
    tqdm_kwargs = {"total": len(coros)}
    if desc:
        tqdm_kwargs["desc"] = desc
    for coro in tqdm(asyncio.as_completed(coros), **tqdm_kwargs):
        results.append(await coro)
    return results


DATA_DIR = Path(__file__).parent / "synthetic" / "data"
DEFAULT_DATA = DATA_DIR / "evals_run_sample.json"


def load_entries(data_path: Path, limit: int | None) -> list[dict]:
    """Read an evals_run_*.json file, optionally keeping only the first N."""
    entries = json.loads(Path(data_path).read_text())
    return entries[:limit] if limit is not None else entries

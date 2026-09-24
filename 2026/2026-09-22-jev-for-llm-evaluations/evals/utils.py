"""Small helpers shared across eval scripts."""

import asyncio

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

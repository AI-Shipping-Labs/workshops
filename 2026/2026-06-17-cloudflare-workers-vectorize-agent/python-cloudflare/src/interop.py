import json

from js import Object
from pyodide.ffi import to_js as _to_js


def to_js(value):
    """Converts Python dicts/lists into JavaScript objects for Worker bindings."""

    return _to_js(value, dict_converter=Object.fromEntries)


def to_py(value):
    """Converts Pyodide JavaScript proxies into regular Python values."""

    if value is None:
        return None

    converter = getattr(value, "to_py", None)
    if callable(converter):
        return converter()

    return value


def env_value(env, name: str, fallback: str) -> str:
    """Reads a Worker env var from the Python FFI env object with a fallback."""

    return str(to_py(getattr(env, name, None)) or fallback)


def parse_jsonish(value) -> dict:
    """Normalizes JSON strings, JS proxies, or dicts into a Python dict."""

    normalized = to_py(value)
    if isinstance(normalized, dict):
        return normalized
    if isinstance(normalized, str):
        return json.loads(normalized)
    return {}

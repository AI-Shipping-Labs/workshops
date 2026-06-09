"""Shared configuration for the ingest and serve processes.

Both `ingest.py` (which builds the SQLite indexes) and `search.py` (which the
server reads from) import these constants so the two processes agree on where
the model and database files live.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# --- FAQ data source ---
FAQ_URL = "https://datatalks.club/faq/json/data-engineering-zoomcamp.json"
COURSE = "data-engineering-zoomcamp"

# --- Embedding model (ONNX, no PyTorch) ---
MODEL_REPO = "Xenova/all-MiniLM-L6-v2"
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / MODEL_REPO

# --- SQLite database ---
# Vector search only for now, so a single SQLite file is enough. Combining text
# (FTS5) and vector indexes in one file currently collides on a shared `docs`
# table; tracked at https://github.com/alexeygrigorev/sqlitesearch/issues/2
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "faq.db"

# --- Index field configuration ---
KEYWORD_FIELDS = ["course"]

# --- Turso (remote libSQL) ---
# When TURSO_DATABASE_URL is set, the index is backed by Turso via a local
# embedded replica: reads/writes hit REPLICA_PATH locally and sync to Turso, so
# the data persists even though the host's disk is ephemeral. Without it, we
# fall back to a plain local SQLite file at DB_PATH (handy for offline dev).
TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
REPLICA_PATH = os.environ.get("REPLICA_PATH", str(DATA_DIR / "faq-replica.db"))

# LSH params tuned for a small (~hundreds of docs) corpus. Kept here so ingest
# and serve build the index identically.
_INDEX_KWARGS = dict(mode="lsh", keyword_fields=KEYWORD_FIELDS, hash_size=8, n_probe=4)


def open_vector_index(local: bool = False):
    """Open the LSH vector index. Both `ingest.py` and `search.py` go through
    this so their index settings can never drift apart.

    Serving (default) opens a Turso-backed embedded replica when configured:
    data syncs down once and reads run against the local file. Ingest passes
    ``local=True`` to build a plain local SQLite file (fast) — that file is then
    imported into Turso in one shot, because writing through the replica
    forwards every INSERT to the remote and is far too slow for bulk loads.
    """
    from sqlitesearch import VectorSearchIndex

    if TURSO_DATABASE_URL and not local:
        Path(REPLICA_PATH).parent.mkdir(parents=True, exist_ok=True)
        return VectorSearchIndex(
            db_path=REPLICA_PATH,
            sync_url=TURSO_DATABASE_URL,
            auth_token=TURSO_AUTH_TOKEN,
            **_INDEX_KWARGS,
        )
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return VectorSearchIndex(db_path=str(DB_PATH), **_INDEX_KWARGS)

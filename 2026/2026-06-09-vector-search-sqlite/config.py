"""Shared configuration for the ingest and serve processes.

Both `ingest.py` (which builds the SQLite indexes) and `search.py` (which the
server reads from) import these constants so the two processes agree on where
the model and database files live.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlitesearch import VectorSearchIndex

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
# Vector search only for this workshop, so a single SQLite file is enough.
# sqlitesearch can also keep a text (FTS5) index and a vector index in one file
# for hybrid search; we stick to vector search here.
DATA_DIR = BASE_DIR / "data"

# --- Index field configuration ---
KEYWORD_FIELDS = ["course"]

# --- Database location (local file or remote Turso) ---
# DB_PATH selects the database: a local SQLite file (handy for offline dev) or a
# `libsql://` URL for a hosted Turso database. With a `libsql://` URL,
# sqlitesearch sets up the embedded replica transparently — reads/writes run
# locally and sync to Turso, so the data persists even on an ephemeral host.
DB_PATH = os.environ.get("DB_PATH", str(DATA_DIR / "faq.db"))
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")  # only needed for a remote

# LSH params tuned for a small (~hundreds of docs) corpus. Kept here so ingest
# and serve build the index identically.
_INDEX_KWARGS = dict(mode="lsh", keyword_fields=KEYWORD_FIELDS, hash_size=8, n_probe=4)


def open_vector_index():
    """Open the LSH vector index. Both `ingest.py` and `search.py` go through
    this so their index settings can never drift apart.

    DB_PATH decides where the index lives: a local SQLite file, or a `libsql://`
    Turso URL. For a Turso URL, sqlitesearch transparently sets up the embedded
    replica (local reads/writes that sync to Turso). The local parent directory
    is created automatically when DB_PATH is a file path.
    """
    return VectorSearchIndex(db_path=DB_PATH, auth_token=TURSO_AUTH_TOKEN, **_INDEX_KWARGS)

# SpireMind RAG Database Setup (SQL Server 2025)

This guide walks you through creating a SQL Server vector store for relic lookups and wiring it into SpireMind.

## Prerequisites

- SQL Server 2025 (or a version with vector support/features)
- Microsoft ODBC Driver for SQL Server installed
- Python `pyodbc` package installed: `pip install pyodbc`
- Ollama running with an embeddings-capable model: `ollama serve && ollama pull llama3`
- SpireMind environment variables configured:
  - `SQLSERVER_CONN_STR` (ODBC connection string)
  - `RAG_EMBED_MODEL` (default `llama3`, the model used to produce embeddings)

## Connection String Example

Set `SQLSERVER_CONN_STR` in your environment.

Windows PowerShell:

```powershell
$env:SQLSERVER_CONN_STR = "Driver={ODBC Driver 18 for SQL Server};Server=YOUR_SERVER;Database=YOUR_DB;UID=USER;PWD=PASS;Encrypt=yes;TrustServerCertificate=yes"
```

Linux/macOS bash:

```bash
export SQLSERVER_CONN_STR="Driver={ODBC Driver 18 for SQL Server};Server=YOUR_SERVER;Database=YOUR_DB;UID=USER;PWD=PASS;Encrypt=yes;TrustServerCertificate=yes"
```

Replace `YOUR_SERVER`, `YOUR_DB`, `USER`, `PASS` accordingly.

## Database Schema

Create tables to hold relics, cards, and events with stored embeddings.

```sql
CREATE TABLE dbo.relics (
  name NVARCHAR(200) NOT NULL PRIMARY KEY,
  description NVARCHAR(MAX) NOT NULL,
  type NVARCHAR(100) NULL,
  tags NVARCHAR(400) NULL,
  embedding VARBINARY(MAX) NOT NULL
);

CREATE TABLE dbo.cards (
  name NVARCHAR(200) NOT NULL PRIMARY KEY,
  description NVARCHAR(MAX) NOT NULL,
  character NVARCHAR(50) NULL,
  cost INT NULL,
  type NVARCHAR(100) NULL,
  tags NVARCHAR(400) NULL,
  embedding VARBINARY(MAX) NOT NULL
);

CREATE TABLE dbo.events (
  name NVARCHAR(200) NOT NULL PRIMARY KEY,
  description NVARCHAR(MAX) NOT NULL,
  tags NVARCHAR(400) NULL,
  embedding VARBINARY(MAX) NOT NULL
);
```

### Vector Index / ANN Support

Use SQL Server 2025’s native vector type and ANN search for best performance.

Store embeddings as `VARBINARY(MAX)` packed as float32; then query with the native cosine distance operator and ANN hint.

Example ANN query used by SpireMind (configurable via `SQLSERVER_VECTOR_SEARCH_SQL`):

```sql
SELECT TOP 1 name, description
FROM dbo.relics WITH (ANN_SEARCH=ON)
ORDER BY VECTOR_COSINE_DISTANCE(embedding, ?) ASC;
```

Notes:

- The parameter `?` must be a binary blob of float32 values (little‑endian) matching the stored embedding dimension.
- Create a vector index per SQL Server 2025 documentation to accelerate ANN queries.

## Embeddings Ingestion

Use the same embedding model as SpireMind (`RAG_EMBED_MODEL`) to embed descriptions for each entity type, pack as float32, then insert into the respective table.

Python example (run once to ingest):

```python
import os, json, struct
import pyodbc
import ollama

CONN = os.getenv("SQLSERVER_CONN_STR")
MODEL = os.getenv("RAG_EMBED_MODEL", "llama3")

relics = [
    {"name": "Kunai", "description": "Gain 1 Dexterity every 3 attacks you play."},
    {"name": "Shuriken", "description": "Gain 1 Strength every 3 attacks you play."},
]
cards = [
    {"name": "Heavy Blade", "description": "Deal damage. Strength affects damage more."},
    {"name": "Backflip", "description": "Gain block and draw cards."},
]
events = [
    {"name": "The Cleric", "description": "Pay gold to remove a card or heal."},
    {"name": "World of Goop", "description": "Encounter slime. Choices affect gold and HP."},
]

def to_bytes(vec):
    # Pack float32 little‑endian
    return struct.pack('<' + 'f' * len(vec), *vec)

def embed(text):
    res = ollama.embed(model=MODEL, input=text)
    return res.get("embedding") or (res.get("embeddings") or [[]])[0]

cn = pyodbc.connect(CONN)
cur = cn.cursor()

for r in relics:
    vec = embed(r["description"]) or []
    cur.execute(
        "INSERT INTO dbo.relics(name, description, embedding) VALUES (?, ?, ?)",
        (r["name"], r["description"], to_bytes(vec)),
    )

cn.commit()

# Cards
cur = cn.cursor()
for c in cards:
    vec = embed(c["description"]) or []
    cur.execute(
        "INSERT INTO dbo.cards(name, description, embedding) VALUES (?, ?, ?)",
        (c["name"], c["description"], to_bytes(vec)),
    )
cn.commit()

# Events
cur = cn.cursor()
for e in events:
    vec = embed(e["description"]) or []
    cur.execute(
        "INSERT INTO dbo.events(name, description, embedding) VALUES (?, ?, ?)",
        (e["name"], e["description"], to_bytes(vec)),
    )
cn.close()
print("Done.")
```

## Wiring Into SpireMind

The agent uses `src/utils/rag.py::RelicRAG`:

- Reads `SQLSERVER_CONN_STR` and `RAG_EMBED_MODEL`
- Tries exact match: `SELECT description FROM dbo.relics WHERE LOWER(name)=LOWER(?)`
- Else embeds the query and runs a top‑1 vector search (placeholder UDF)
- Falls back to `relics_cache.json` in repo root if DB/driver is unavailable

## Verification

1. Ensure `SQLSERVER_CONN_STR` is set and `dbo.relics` has rows
2. Run the bot and visit a shop: `python src/main.py`
3. Check logs for RAG activity and “RAG NOTES” in the agent’s prompt

## Troubleshooting

- `pyodbc` driver errors: install the correct ODBC driver and verify the DSN/Driver name
- Embedding errors: ensure Ollama is running and the model supports embeddings
- Query performance: replace the placeholder cosine UDF with native SQL Server 2025 vector functions and indexes

## Next Steps

- Ingest the full Slay the Spire relic wiki (name + description) and build embeddings in batches
- Add tables for cards and events, and update `RelicRAG` to a unified `GameRAG` service
- Move from JSON-stored embeddings to a true binary packing aligned with SQL Server’s vector features

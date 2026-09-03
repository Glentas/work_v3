# Information Retrieval System

A small FastAPI-based information retrieval system with logical search, relevance marking, and ROMIP/TREC metrics.

## Setup

```bash
git clone <repository-url>
cd lab1-search
uv sync
```

## Prepare documents

Place English documents in the `collection/` folder.

Supported formats:

```text
.txt
.pdf
```

## Run

```bash
uv run python run.py
```

Open:

```text
http://localhost:8000
```

## First steps

1. Click `Reindex`.
2. Enter an English search query.
3. Mark relevant documents using checkboxes.
4. Click `Save evaluation`.
5. Open `Metrics` to view tables and graphs.

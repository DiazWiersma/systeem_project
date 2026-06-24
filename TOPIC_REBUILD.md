# Rebuild chunk-topic evidence

This is a one-time, reproducible rebuild. It does **not** overwrite the working
database. It creates `backend/ungdc_rebuilt.db`, which is compatible with the
current site and can be swapped in after validation.

## What stays unchanged

- All speeches and full text
- Existing primary and secondary speech-topic assignments
- Topic, country, year, map, and timeline statistics
- Every existing API endpoint

Only `chunk_topics_new` is rebuilt. Every 150-word chunk retains its three best
semantic topic matches and scores. Every topic already assigned to a speech is
also guaranteed to receive its best supporting chunk. Low-confidence evidence is
retained and labelled instead of silently discarded.

## 1. Stop the website

Stop the running backend before the final database swap. The rebuild itself may
run while the website is open because it writes a different file.

## 2. Create a rebuild environment

From the repository root on Windows PowerShell:

```powershell
cd backend
python -m venv .venv-rebuild
.\.venv-rebuild\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-rebuild.txt
```

The first run downloads the `all-MiniLM-L6-v2` sentence-transformer model. A CUDA
GPU is strongly recommended for the 271,959 chunks, although CPU mode also works.

## 3. Build the replacement database

Automatic device selection:

```powershell
python rebuild_chunk_topics.py
```

Explicit NVIDIA GPU with a larger batch:

```powershell
python rebuild_chunk_topics.py --device cuda --batch-size 1024
```

CPU with a smaller batch:

```powershell
python rebuild_chunk_topics.py --device cpu --batch-size 256
```

The source remains `ungdc.db`; the output is `ungdc_rebuilt.db`. Rerunning when
the output already exists requires `--overwrite`.

## 4. Check the result

A successful run ends with:

- SQLite integrity check: `ok`
- zero speech-topic assignments without evidence
- the number of encoded chunks and evidence rows
- the number of retained low-confidence rows

Do not swap databases if the script reports an error.

## 5. Swap the database

With the website stopped and while still inside `backend`:

```powershell
Move-Item -LiteralPath ungdc.db -Destination ungdc_before_rebuild.db
Move-Item -LiteralPath ungdc_rebuilt.db -Destination ungdc.db
```

Restart the website normally. No code or configuration change is required.

## Roll back

Stop the website, then:

```powershell
Move-Item -LiteralPath ungdc.db -Destination ungdc_rebuilt_failed.db
Move-Item -LiteralPath ungdc_before_rebuild.db -Destination ungdc.db
```

## Reproducibility metadata

The rebuilt database contains `topic_rebuild_meta`, recording the model, chunk
size, overlap, top-k value, confidence threshold, row count, and build timestamp.

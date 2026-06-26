from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from pathlib import Path


WORDS_PER_CHUNK = 150
CHUNK_OVERLAP = 30


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Build a drop-in database with complete chunk-topic evidence."
    )
    parser.add_argument("--source", type=Path, default=here / "ungdc.db")
    parser.add_argument("--output", type=Path, default=here / "ungdc_rebuilt.db")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, or mps")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.42,
        help="Marks evidence as low-confidence; rows are never discarded.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def chunk_text(text: str):
    words = str(text or "").split()
    start = 0
    chunk_idx = 0
    step = WORDS_PER_CHUNK - CHUNK_OVERLAP
    while start < len(words):
        end = start + WORDS_PER_CHUNK
        yield chunk_idx, " ".join(words[start:end])
        if end >= len(words):
            break
        start += step
        chunk_idx += 1


def has_table(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def copy_database(source: Path, output: Path, overwrite: bool) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Source database not found: {source}")
    if source.resolve() == output.resolve():
        raise ValueError("Source and output must be different files.")
    if output.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output already exists: {output}. Use --overwrite to replace it."
            )
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(output) as dst:
        src.backup(dst)


def load_topics(con: sqlite3.Connection):
    if has_table(con, "topic_meta"):
        rows = con.execute(
            "SELECT topic, topic_label, description, keywords "
            "FROM topic_meta ORDER BY topic"
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT topic, topic_label, '', '' FROM topics ORDER BY topic"
        ).fetchall()
    if not rows:
        raise RuntimeError("No topic definitions found in topic_meta or topics.")
    topic_ids = [int(row[0]) for row in rows]
    labels = [str(row[1] or f"Topic {row[0]}") for row in rows]
    texts = []
    for topic_id, label, description, keywords in rows:
        parts = [str(description or "").strip(), str(keywords or "").strip(), str(label)]
        texts.append(". ".join(part for part in parts if part))
    return topic_ids, labels, texts


def load_assignments(con: sqlite3.Connection):
    assignments: dict[int, list[int]] = {}
    if has_table(con, "speech_topics"):
        rows = con.execute(
            "SELECT s.rowid, st.topic FROM speeches s "
            "JOIN speech_topics st ON st.iso=s.iso AND st.year=s.year "
            "ORDER BY s.rowid, st.rank"
        )
        for speech_id, topic in rows:
            assignments.setdefault(int(speech_id), []).append(int(topic))
    for speech_id, topic in con.execute(
        "SELECT rowid, topic_final FROM speeches WHERE topic_final IS NOT NULL "
        "AND topic_final != -1"
    ):
        bucket = assignments.setdefault(int(speech_id), [])
        if int(topic) not in bucket:
            bucket.insert(0, int(topic))
    return assignments


def prepare_staging(con: sqlite3.Connection) -> None:
    con.execute("DROP TABLE IF EXISTS chunk_topics_rebuilt")
    con.execute(
        """
        CREATE TABLE chunk_topics_rebuilt (
            speech_id INTEGER NOT NULL,
            chunk_idx INTEGER NOT NULL,
            topic_final INTEGER NOT NULL,
            topic_label TEXT NOT NULL,
            score REAL NOT NULL,
            evidence_kind TEXT NOT NULL,
            is_low_confidence INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (speech_id, chunk_idx, topic_final)
        )
        """
    )
    con.commit()


def select_device(requested: str) -> str:
    if requested != "auto":
        return requested
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def rebuild(args: argparse.Namespace) -> None:
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Missing rebuild dependencies. Install backend/requirements-rebuild.txt"
        ) from exc

    copy_database(args.source, args.output, args.overwrite)
    con = sqlite3.connect(args.output)
    read_con = sqlite3.connect(args.source)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    topic_ids, topic_labels, topic_texts = load_topics(con)
    topic_index = {topic_id: idx for idx, topic_id in enumerate(topic_ids)}
    assignments = load_assignments(con)
    prepare_staging(con)

    device = select_device(args.device)
    print(f"Loading {args.model} on {device}...")
    model = SentenceTransformer(args.model, device=device)
    topic_embeddings = model.encode(
        topic_texts, normalize_embeddings=True, batch_size=args.batch_size
    )
    topic_embeddings = np.asarray(topic_embeddings, dtype=np.float32)

    total_speeches = con.execute("SELECT COUNT(*) FROM speeches").fetchone()[0]
    processed_speeches = 0
    processed_chunks = 0
    inserted_rows = 0
    started = time.time()
    best_evidence: dict[tuple[int, int], tuple[float, int]] = {}

    batch_texts: list[str] = []
    batch_meta: list[tuple[int, int]] = []

    def flush_batch() -> None:
        nonlocal processed_chunks, inserted_rows
        if not batch_texts:
            return
        embeddings = model.encode(
            batch_texts,
            normalize_embeddings=True,
            batch_size=args.batch_size,
            show_progress_bar=False,
        )
        scores = np.asarray(embeddings, dtype=np.float32) @ topic_embeddings.T
        k = min(max(1, args.top_k), len(topic_ids))
        top = np.argpartition(scores, -k, axis=1)[:, -k:]
        rows = []
        for local_idx, (speech_id, chunk_idx) in enumerate(batch_meta):
            ranked = top[local_idx][np.argsort(scores[local_idx, top[local_idx]])[::-1]]
            for topic_pos in ranked:
                score = float(scores[local_idx, topic_pos])
                rows.append(
                    (
                        speech_id,
                        chunk_idx,
                        topic_ids[topic_pos],
                        topic_labels[topic_pos],
                        score,
                        "top_k",
                        int(score < args.confidence_threshold),
                    )
                )
            for assigned_topic in assignments.get(speech_id, []):
                topic_pos = topic_index.get(assigned_topic)
                if topic_pos is None:
                    continue
                score = float(scores[local_idx, topic_pos])
                key = (speech_id, assigned_topic)
                previous = best_evidence.get(key)
                if previous is None or score > previous[0]:
                    best_evidence[key] = (score, chunk_idx)
        con.executemany(
            "INSERT OR REPLACE INTO chunk_topics_rebuilt VALUES (?,?,?,?,?,?,?)", rows
        )
        inserted_rows += len(rows)
        processed_chunks += len(batch_texts)
        batch_texts.clear()
        batch_meta.clear()

    speech_rows = read_con.execute("SELECT rowid, text FROM speeches ORDER BY rowid")
    for speech_id, text in speech_rows:
        for chunk_idx, chunk in chunk_text(text):
            batch_texts.append(chunk)
            batch_meta.append((int(speech_id), int(chunk_idx)))
            if len(batch_texts) >= args.batch_size:
                flush_batch()
        processed_speeches += 1
        if processed_speeches % 250 == 0:
            elapsed = max(time.time() - started, 0.001)
            rate = processed_speeches / elapsed
            eta = (total_speeches - processed_speeches) / max(rate, 0.001)
            print(
                f"{processed_speeches:,}/{total_speeches:,} speeches; "
                f"{processed_chunks:,} chunks; ETA {eta / 60:.1f} min"
            )
            con.commit()
    flush_batch()
    read_con.close()

    evidence_rows = []
    for (speech_id, topic_id), (score, chunk_idx) in best_evidence.items():
        topic_pos = topic_index[topic_id]
        evidence_rows.append(
            (
                speech_id,
                chunk_idx,
                topic_id,
                topic_labels[topic_pos],
                score,
                "assigned_best",
                int(score < args.confidence_threshold),
            )
        )
    con.executemany(
        "INSERT OR IGNORE INTO chunk_topics_rebuilt VALUES (?,?,?,?,?,?,?)",
        evidence_rows,
    )
    con.commit()

    missing = con.execute(
        """
        SELECT COUNT(*) FROM speech_topics st
        JOIN speeches s ON s.iso=st.iso AND s.year=st.year
        WHERE NOT EXISTS (
            SELECT 1 FROM chunk_topics_rebuilt c
            WHERE c.speech_id=s.rowid AND c.topic_final=st.topic
        )
        """
    ).fetchone()[0] if has_table(con, "speech_topics") else 0
    if missing:
        raise RuntimeError(f"Validation failed: {missing} speech-topic links lack evidence")
    missing_primary = con.execute(
        """
        SELECT COUNT(*) FROM speeches s
        WHERE s.topic_final IS NOT NULL AND s.topic_final != -1
          AND NOT EXISTS (
            SELECT 1 FROM chunk_topics_rebuilt c
            WHERE c.speech_id=s.rowid AND c.topic_final=s.topic_final
          )
        """
    ).fetchone()[0]
    if missing_primary:
        raise RuntimeError(
            f"Validation failed: {missing_primary} primary topics lack evidence"
        )

    with con:
        con.execute("DROP TABLE IF EXISTS chunk_topics_new")
        con.execute("ALTER TABLE chunk_topics_rebuilt RENAME TO chunk_topics_new")
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunk_speech_topic "
            "ON chunk_topics_new(speech_id, topic_final)"
        )
        con.execute("DROP TABLE IF EXISTS topic_rebuild_meta")
        con.execute("CREATE TABLE topic_rebuild_meta (key TEXT PRIMARY KEY, value TEXT)")
        metadata = {
            "model": args.model,
            "words_per_chunk": WORDS_PER_CHUNK,
            "overlap": CHUNK_OVERLAP,
            "top_k": args.top_k,
            "confidence_threshold": args.confidence_threshold,
            "chunks": processed_chunks,
            "rows": con.execute("SELECT COUNT(*) FROM chunk_topics_new").fetchone()[0],
            "built_at_unix": int(time.time()),
        }
        con.executemany(
            "INSERT INTO topic_rebuild_meta VALUES (?,?)",
            [(key, json.dumps(value)) for key, value in metadata.items()],
        )
        con.execute("PRAGMA optimize")

    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    rows = con.execute("SELECT COUNT(*) FROM chunk_topics_new").fetchone()[0]
    low = con.execute(
        "SELECT COUNT(*) FROM chunk_topics_new WHERE is_low_confidence=1"
    ).fetchone()[0]
    con.close()
    if integrity != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")

    print("\nRebuild complete")
    print(f"Output: {args.output}")
    print(f"Chunks encoded: {processed_chunks:,}")
    print(f"Evidence rows: {rows:,}")
    print(f"Low-confidence rows retained: {low:,}")
    print("All existing speech-topic assignments have supporting evidence.")


def main() -> int:
    args = parse_args()
    try:
        rebuild(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

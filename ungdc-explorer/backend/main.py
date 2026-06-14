from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import pandas as pd
from pathlib import Path

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "ungdc.db"

def get_db():
    return sqlite3.connect(DB_PATH)


@app.get("/topics")
def get_topics():
    df = pd.read_sql("""
        SELECT topic as topic,
               topic_label as clean_name,
               count
        FROM topics
        WHERE count > 0
        ORDER BY count DESC
    """, get_db())
    return df.to_dict(orient="records")


@app.get("/countries")
def get_countries():
    df = pd.read_sql(
        "SELECT DISTINCT iso, country_clean as country FROM speeches ORDER BY country_clean",
        get_db()
    )
    return df.to_dict(orient="records")


@app.get("/speeches")
def get_speeches(
    iso: str = Query(None),
    topic: int = Query(None),
    year_from: int = Query(None),
    year_to: int = Query(None)
):
    query = """
        SELECT iso, country, year, session, speaker, post,
               topic_final, topic_final_name
        FROM speeches
        WHERE 1=1
    """
    params = []
    if iso:
        query += " AND iso = ?"
        params.append(iso)
    if topic is not None:
        query += " AND topic_final = ?"
        params.append(topic)
    if year_from:
        query += " AND year >= ?"
        params.append(year_from)
    if year_to:
        query += " AND year <= ?"
        params.append(year_to)
    query += " ORDER BY year DESC"
    df = pd.read_sql(query, get_db(), params=params)
    return df.to_dict(orient="records")


@app.get("/speech/{iso}/{year}")
def get_speech(iso: str, year: int):
    df = pd.read_sql(
        "SELECT * FROM speeches WHERE iso = ? AND year = ?",
        get_db(), params=[iso, year]
    )
    if df.empty:
        return {"error": "Niet gevonden"}
    return df.iloc[0].to_dict()


@app.get("/timeline")
def get_timeline(topic: int = Query(None)):
    if topic is not None:
        df = pd.read_sql(
            "SELECT year, count, share FROM topic_year WHERE topic = ? ORDER BY year",
            get_db(), params=[topic]
        )
    else:
        df = pd.read_sql(
            "SELECT year, SUM(count) as count FROM topic_year GROUP BY year ORDER BY year",
            get_db()
        )
    return df.to_dict(orient="records")


@app.get("/country-topics/{iso}")
def get_country_topics(iso: str):
    df = pd.read_sql(
        """SELECT topic, topic_label, count, total_speeches, share
           FROM country_topic
           WHERE iso = ?
           ORDER BY count DESC""",
        get_db(), params=[iso]
    )
    return df.to_dict(orient="records")


@app.get("/speech/{iso}/{year}/highlights")
def get_highlights(iso: str, year: int, topic: int = Query(None)):
    db = get_db()

    # get speech rowid and text
    df = pd.read_sql(
        "SELECT rowid as speech_id, text, topic_final, topic_final_name FROM speeches WHERE iso = ? AND year = ?",
        db, params=[iso, year]
    )
    if df.empty:
        return {"error": "Niet gevonden"}

    row = df.iloc[0]
    text = row["text"]
    speech_id = int(row["speech_id"])
    topic_id = topic if topic is not None else int(row["topic_final"])

    # get matched chunks for this speech and topic
    chunks_df = pd.read_sql("""
        SELECT chunk_idx, score
        FROM chunk_topics_new
        WHERE speech_id = ? AND topic_final = ?
        ORDER BY chunk_idx
    """, db, params=[speech_id, topic_id])

    if chunks_df.empty:
        return {
            "iso": iso, "year": year, "topic": topic_id,
            "highlights": [], "total_chunks": 0, "highlighted_chunks": 0
        }

    # rebuild chunks from text (must match chunking params used during embedding)
    def chunk_text(text, words_per_chunk=150, overlap=30):
        words = text.split()
        chunks = []
        start = 0
        while start < len(words):
            end = start + words_per_chunk
            chunks.append((start, " ".join(words[start:end])))
            start += words_per_chunk - overlap
            if end >= len(words):
                break
        return chunks

    all_chunks = chunk_text(text)
    matched_indices = set(chunks_df["chunk_idx"].tolist())
    scores = dict(zip(chunks_df["chunk_idx"], chunks_df["score"]))

    highlights = []
    for idx, (word_start, chunk_text_str) in enumerate(all_chunks):
        if idx in matched_indices:
            highlights.append({
                "chunk_idx": idx,
                "text": chunk_text_str,
                "score": round(scores[idx], 4),
                "word_start": word_start
            })

    return {
        "iso": iso,
        "year": year,
        "topic": topic_id,
        "total_chunks": len(all_chunks),
        "highlighted_chunks": len(highlights),
        "highlights": highlights
    }
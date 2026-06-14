from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import pandas as pd
from pathlib import Path
import re

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
        SELECT topic_final as topic,
               topic_final_name as clean_name,
               COUNT(*) as count
        FROM speeches
        WHERE topic_final != -1
        GROUP BY topic_final, topic_final_name
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
    # Haal de toespraak op
    df = pd.read_sql(
        "SELECT text, topic_final, topic_final_name FROM speeches WHERE iso = ? AND year = ?",
        get_db(), params=[iso, year]
    )
    if df.empty:
        return {"error": "Niet gevonden"}

    row = df.iloc[0]
    text = row["text"]

    # Haal keywords op uit de topic label
    # label formaat: "0_sustainable_climate_change_climate change"
    topic_id = topic if topic is not None else row["topic_final"]
    label_df = pd.read_sql(
        "SELECT topic_label FROM topics WHERE topic = ?",
        get_db(), params=[int(topic_id)]
    )
    if label_df.empty:
        return {"error": "Topic niet gevonden"}

    # Parse keywords uit label string
    label = label_df.iloc[0]["topic_label"]
    parts = label.split("_")[1:]  # verwijder het nummer vooraan
    keywords = list(set([p.strip() for p in parts if len(p.strip()) > 2]))

    # Zoek zinnen die keywords bevatten
    sentences = re.split(r'(?<=[.!?])\s+', text)
    highlights = []
    cursor = 0

    for s in sentences:
        matched_keywords = [
            kw for kw in keywords
            if re.search(rf'\b{re.escape(kw)}\b', s, re.IGNORECASE)
        ]

        if matched_keywords:
            highlights.append({
                "sentence": s,
                "start": cursor,
                "end": cursor + len(s),
                "matched_keywords": matched_keywords
            })

        cursor += len(s) + 1

    return {
        "iso": iso,
        "year": year,
        "topic": topic_id,
        "keywords": keywords,
        "total_sentences": len(sentences),
        "highlighted_sentences": len(highlights),
        "highlights": highlights
    }
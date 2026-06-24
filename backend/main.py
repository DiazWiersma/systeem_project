# main.py - UNGC Explorer backend (FastAPI + SQLite)
# Alle endpoints van de vorige versie blijven werken; daarnaast:
#   /map           choropleth-aggregatie per land (veel sneller dan client-side tellen)
#   /speeches      ondersteunt nu ook q= (vrij zoekwoord in de speechtekst) en geeft per
#                  speech een lijst met topics terug (meerdere topics per speech mogelijk)
#   /keyword-map   choropleth op basis van een vrij zoekwoord
#   /timeline      ondersteunt nu ook iso= voor de piekjaren per land
#   /status        kleine healthcheck voor de statusknop in de frontend
#
# Topicfilters lopen via de tabel speech_topics (een rij per speech-topickoppeling,
# meerdere topics per speech mogelijk). Dat is veel sneller dan filteren op de
# speeches-tabel zelf, omdat die de volledige teksten bevat. Ontbreekt de tabel
# (oudere database), dan valt alles terug op de kolom topic_final.

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import pandas as pd
from pathlib import Path
import re

app = FastAPI(title="UNGC Explorer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "ungdc.db"


# Presentation-only normalisation. The historical source values stay untouched in
# SQLite, while the API exposes consistent modern names and useful search aliases.
COUNTRY_NAMES = {
    "CSK": ("Czechoslovakia", ["Czech and Slovak Federal Republic"]),
    "DDR": ("East Germany", ["DDR", "German Democratic Republic"]),
    "COD": ("Democratic Republic of the Congo", ["Dem. Rep. Congo", "DR Congo", "DRC", "Zaire"]),
    "COG": ("Republic of the Congo", ["Congo", "Rep. Congo", "Congo-Brazzaville"]),
    "CPV": ("Cape Verde", ["Cabo Verde"]),
    "CIV": ("Côte d'Ivoire", ["Cote d'Ivoire", "Ivory Coast"]),
    "CZE": ("Czechia", ["Czech Republic"]),
    "MKD": ("North Macedonia", ["Macedonia"]),
    "SWZ": ("Eswatini", ["Swaziland", "eSwatini"]),
    "TLS": ("Timor-Leste", ["East Timor"]),
    "YMD": ("South Yemen", ["YMD", "Democratic Yemen", "People's Democratic Republic of Yemen", "Unknown"]),
    "YUG": ("Yugoslavia", ["Serbia and Montenegro"]),
}
HISTORICAL_ISOS = {"CSK", "DDR", "YMD", "YUG"}


def display_speaker(value):
    """Fix known source spelling variants without rewriting the source corpus."""
    if not isinstance(value, str):
        return value
    return re.sub(r"\bErdogan\b", "Erdoğan", value)


def normalise_records(records):
    for record in records:
        if "speaker" in record:
            record["speaker"] = display_speaker(record.get("speaker"))
    return records


def get_db():
    return sqlite3.connect(DB_PATH)


def has_table(con, name):
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def has_column(con, table, column):
    return any(row[1] == column for row in con.execute(f"PRAGMA table_info({table})"))


def topic_join(con, topic, params):
    """JOIN-clausule die speeches beperkt tot een topic. Met speech_topics
    tellen alle topics van een speech mee; anders alleen topic_final."""
    if topic is None:
        return ""
    if has_table(con, "speech_topics"):
        params.insert(0, int(topic))
        return (" JOIN (SELECT DISTINCT iso, year FROM speech_topics WHERE topic = ?) tf"
                " ON tf.iso = s.iso AND tf.year = s.year")
    return ""


def topic_where(con, topic, params):
    """WHERE-toevoeging voor de terugvaloptie zonder speech_topics."""
    if topic is None or has_table(con, "speech_topics"):
        return ""
    params.append(int(topic))
    return " AND s.topic_final = ?"


def q_where(q, params):
    """Vrij zoekwoord in de speechtekst; meerdere woorden = alle woorden moeten voorkomen."""
    sql = ""
    if not q:
        return sql
    for term in q.split():
        term = term.strip()
        if len(term) < 2:
            continue
        sql += " AND s.text LIKE ? COLLATE NOCASE"
        params.append(f"%{term}%")
    return sql


@app.get("/status")
def get_status():
    con = get_db()
    try:
        n_speeches = con.execute("SELECT COUNT(*) FROM speeches").fetchone()[0]
        n_topics = con.execute(
            "SELECT COUNT(DISTINCT topic_final) FROM speeches WHERE topic_final != -1"
        ).fetchone()[0]
        years = con.execute("SELECT MIN(year), MAX(year) FROM speeches").fetchone()
        return {
            "ok": True,
            "speeches": int(n_speeches),
            "topics": int(n_topics),
            "year_from": int(years[0]),
            "year_to": int(years[1]),
            "multi_topic": has_table(con, "speech_topics"),
        }
    finally:
        con.close()


@app.get("/topics")
def get_topics():
    # Leest uit de (door build_db.py consistent opgebouwde) topics-tabel, zodat de
    # tellingen exact overeenkomen met /map, /timeline en /country-topics.
    # count = aantal speeches dat het topic aanraakt (multi-topic).
    con = get_db()
    try:
        df = pd.read_sql("""
            SELECT topic,
                   topic_label as clean_name,
                   count
            FROM topics
            WHERE count > 0
            ORDER BY count DESC
        """, con)
        return df.to_dict(orient="records")
    finally:
        con.close()


@app.get("/topics/details")
def get_topic_details():
    """Volledige topicinfo (label, omschrijving, keywords, count) uit de
    database. Hiermee haalt de frontend de filterlijst en de legenda-tekst
    live op, i.p.v. uit een grote ingebedde CSV."""
    con = get_db()
    try:
        if not has_table(con, "topic_meta"):
            # terugval: alleen label + count uit topics
            df = pd.read_sql(
                "SELECT topic, topic_label as clean_name, '' as description, "
                "'' as keywords, count FROM topics ORDER BY count DESC", con)
            return df.to_dict(orient="records")
        df = pd.read_sql("""
            SELECT topic,
                   topic_label as clean_name,
                   description,
                   keywords,
                   count
            FROM topic_meta
            ORDER BY count DESC
        """, con)
        return df.to_dict(orient="records")
    finally:
        con.close()


@app.get("/countries")
def get_countries():
    con = get_db()
    try:
        rows = con.execute(
            "SELECT iso, MIN(country_clean) FROM speeches "
            "WHERE iso IS NOT NULL GROUP BY iso ORDER BY MIN(country_clean)"
        ).fetchall()
        countries = []
        for iso, source_name in rows:
            display_name, aliases = COUNTRY_NAMES.get(iso, (source_name, []))
            combined_aliases = list(dict.fromkeys(
                [source_name, *aliases] if source_name != display_name else aliases
            ))
            countries.append({
                "iso": iso,
                "country": display_name,
                "aliases": combined_aliases,
                "historical": iso in HISTORICAL_ISOS,
            })
        return sorted(countries, key=lambda item: item["country"])
    finally:
        con.close()


@app.get("/map")
def get_map(
    topic: int = Query(None),
    year_from: int = Query(None),
    year_to: int = Query(None),
    q: str = Query(None),
):
    """Aantal matchende speeches per land, voor de choropleth."""
    con = get_db()
    try:
        params = []
        # Snelste route: topicfilter zonder zoekwoord kan volledig op
        # speech_topics draaien en raakt de zware tekstkolom niet aan.
        if topic is not None and not q and has_table(con, "speech_topics"):
            sql = "SELECT iso, COUNT(*) as count FROM speech_topics WHERE topic = ?"
            params.append(int(topic))
            if year_from:
                sql += " AND year >= ?"
                params.append(year_from)
            if year_to:
                sql += " AND year <= ?"
                params.append(year_to)
            sql += " GROUP BY iso"
            df = pd.read_sql(sql, con, params=params)
            return df.to_dict(orient="records")

        sql = "SELECT s.iso, COUNT(*) as count FROM speeches s"
        sql += topic_join(con, topic, params)
        sql += " WHERE s.iso IS NOT NULL"
        sql += topic_where(con, topic, params)
        if year_from:
            sql += " AND s.year >= ?"
            params.append(year_from)
        if year_to:
            sql += " AND s.year <= ?"
            params.append(year_to)
        sql += q_where(q, params)
        sql += " GROUP BY s.iso"
        df = pd.read_sql(sql, con, params=params)
        return df.to_dict(orient="records")
    finally:
        con.close()


@app.get("/keyword-map")
def get_keyword_map(
    q: str = Query(...),
    year_from: int = Query(None),
    year_to: int = Query(None),
):
    """Choropleth op vrij zoekwoord (zonder topicfilter)."""
    return get_map(topic=None, year_from=year_from, year_to=year_to, q=q)


@app.get("/speeches")
def get_speeches(
    iso: str = Query(None),
    topic: int = Query(None),
    year_from: int = Query(None),
    year_to: int = Query(None),
    q: str = Query(None),
    limit: int = Query(None),
):
    con = get_db()
    try:
        multi = has_table(con, "speech_topics")
        params = []
        topics_col = (
            ", (SELECT GROUP_CONCAT(st.topic || '::' || st.topic_label, '||') "
            "FROM speech_topics st WHERE st.iso = s.iso AND st.year = s.year) as topics_all"
        ) if multi else ""
        sql = (f"SELECT s.iso, s.country, s.year, s.session, s.speaker, s.post,"
               f" s.topic_final, s.topic_final_name{topics_col} FROM speeches s")
        sql += topic_join(con, topic, params)
        sql += " WHERE 1=1"
        sql += topic_where(con, topic, params)
        if iso:
            sql += " AND s.iso = ?"
            params.append(iso)
        if year_from:
            sql += " AND s.year >= ?"
            params.append(year_from)
        if year_to:
            sql += " AND s.year <= ?"
            params.append(year_to)
        sql += q_where(q, params)
        sql += " ORDER BY s.year DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        df = pd.read_sql(sql, con, params=params)
        return normalise_records(df.to_dict(orient="records"))
    finally:
        con.close()


@app.get("/speech/{iso}/{year}")
def get_speech(iso: str, year: int):
    con = get_db()
    try:
        df = pd.read_sql(
            "SELECT * FROM speeches WHERE iso = ? AND year = ?",
            con, params=[iso, year]
        )
        if df.empty:
            return {"error": "Niet gevonden"}
        rec = df.iloc[0].to_dict()
        rec["speaker"] = display_speaker(rec.get("speaker"))
        if has_table(con, "speech_topics"):
            tdf = pd.read_sql(
                "SELECT topic, topic_label, rank FROM speech_topics "
                "WHERE iso = ? AND year = ? ORDER BY rank",
                con, params=[iso, year]
            )
            rec["topics"] = tdf.to_dict(orient="records")
        return rec
    finally:
        con.close()


@app.get("/timeline")
def get_timeline(topic: int = Query(None), iso: str = Query(None)):
    """Aantal speeches per jaar. Zonder iso: wereldwijd (zoals voorheen).
    Met iso: alleen voor dat land, voor de piekperiode per land."""
    con = get_db()
    try:
        if iso:
            if topic is not None and has_table(con, "speech_topics"):
                df = pd.read_sql(
                    "SELECT year, COUNT(*) as count FROM speech_topics "
                    "WHERE iso = ? AND topic = ? GROUP BY year ORDER BY year",
                    con, params=[iso, int(topic)]
                )
            else:
                params = [iso]
                sql = ("SELECT s.year, COUNT(*) as count FROM speeches s "
                       "WHERE s.iso = ?")
                if topic is not None:
                    sql += " AND s.topic_final = ?"
                    params.append(int(topic))
                sql += " GROUP BY s.year ORDER BY s.year"
                df = pd.read_sql(sql, con, params=params)
            return df.to_dict(orient="records")
        if topic is not None:
            df = pd.read_sql(
                "SELECT year, count, share FROM topic_year WHERE topic = ? ORDER BY year",
                con, params=[int(topic)]
            )
        else:
            df = pd.read_sql(
                "SELECT year, SUM(count) as count FROM topic_year GROUP BY year ORDER BY year",
                con
            )
        return df.to_dict(orient="records")
    finally:
        con.close()


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


def _chunk_text(text, words_per_chunk=150, overlap=30):
    """Identiek aan de chunking in build_db.py / better_topics.ipynb. Geeft per
    chunk de woord-startindex en de tekst terug."""
    words = str(text).split()
    chunks, start = [], 0
    while start < len(words):
        end = start + words_per_chunk
        chunks.append((start, " ".join(words[start:end])))
        start += words_per_chunk - overlap
        if end >= len(words):
            break
    return chunks


def _chunk_end(word_start, text):
    return word_start + len(str(text).split())


def _topic_keywords(con, topic_id):
    """Keywords van een topic voor de gele markering. Eerst de echte keywords
    uit topic_meta (door build_db.py opgeslagen); anders afgeleid uit het label
    (ruw BERTopic-label of schoon label)."""
    if has_table(con, "topic_meta"):
        row = con.execute("SELECT keywords FROM topic_meta WHERE topic = ?",
                          (int(topic_id),)).fetchone()
        if row and row[0]:
            kws = [k.strip() for k in str(row[0]).split(",") if len(k.strip()) > 2]
            if kws:
                return list(dict.fromkeys(kws))      # uniek, volgorde behouden
    row = con.execute("SELECT topic_label FROM topics WHERE topic = ?",
                       (int(topic_id),)).fetchone()
    if not row:
        return []
    label = row[0] or ""
    if "_" in label:                       # ruw label: "0_climate_change_..."
        parts = label.split("_")[1:]
    else:                                  # schoon label: "Climate Change & ..."
        parts = re.split(r"[\s&/,–-]+", label)
    return list({p.strip() for p in parts if len(p.strip()) > 2})


@app.get("/speech/{iso}/{year}/highlights")
def get_highlights(iso: str, year: int, topic: int = Query(None), q: str = Query(None)):
    """Gemarkeerde passages in een speech.
      - chunk_topics_new aanwezig  -> chunk-gebaseerd: geeft de chunks terug die
        het model aan dit topic koppelde, met score.
      - anders                     -> zin-gebaseerde terugval op keywordmatch.
      - q (vrij zoekwoord)         -> altijd zin-gebaseerd op de zoektermen.
    Elke highlight bevat altijd 'text' (+ 'sentence' als alias), zodat de
    frontend met beide vormen overweg kan."""
    con = get_db()
    try:
        df = pd.read_sql(
            "SELECT rowid as speech_id, text, topic_final, topic_final_name "
            "FROM speeches WHERE iso = ? AND year = ?",
            con, params=[iso, year])
        if df.empty:
            return {"error": "Niet gevonden"}
        row = df.iloc[0]
        text = row["text"]
        speech_id = int(row["speech_id"])
        topic_id = topic if topic is not None else int(row["topic_final"])

        chunk_mode = (not q) and has_table(con, "chunk_topics_new")

        if chunk_mode:
            evidence_cols = (
                ", evidence_kind, is_low_confidence"
                if has_column(con, "chunk_topics_new", "evidence_kind")
                else ", 'top_k' as evidence_kind, 0 as is_low_confidence"
            )
            cdf = pd.read_sql(
                "SELECT chunk_idx, score" + evidence_cols + " FROM chunk_topics_new "
                "WHERE speech_id = ? AND topic_final = ? "
                "ORDER BY score DESC, chunk_idx",
                con, params=[speech_id, int(topic_id)])
            chunks = _chunk_text(text)
            matched = set(cdf["chunk_idx"].tolist())
            scores = dict(zip(cdf["chunk_idx"], cdf["score"]))
            evidence_kinds = dict(zip(cdf["chunk_idx"], cdf["evidence_kind"]))
            low_confidence = dict(zip(cdf["chunk_idx"], cdf["is_low_confidence"]))
            highlights = []
            for idx, (word_start, chunk_str) in enumerate(chunks):
                if idx in matched:
                    highlights.append({
                        "chunk_idx": idx,
                        "text": chunk_str,
                        "sentence": chunk_str,            # alias
                        "score": round(float(scores[idx]), 4),
                        "evidence_kind": evidence_kinds[idx],
                        "is_low_confidence": bool(low_confidence[idx]),
                        "word_start": word_start,
                        "word_end": _chunk_end(word_start, chunk_str),
                        "matched_keywords": [],
                    })
            highlights.sort(
                key=lambda item: (-float(item["score"]), int(item["chunk_idx"]))
            )
            if highlights:
                return {
                    "iso": iso, "year": year, "topic": int(topic_id), "mode": "chunk",
                    "keywords": [],
                    "total_chunks": len(chunks),
                    "highlighted_chunks": len(highlights),
                    "total_sentences": len(chunks),           # voor compat
                    "highlighted_sentences": len(highlights),
                    "highlights": highlights,
                }
            fallback = chunks[0] if chunks else (0, str(text))
            return {
                "iso": iso, "year": year, "topic": int(topic_id), "mode": "speech",
                "keywords": [],
                "total_chunks": len(chunks),
                "highlighted_chunks": 0,
                "total_sentences": len(chunks),
                "highlighted_sentences": 0,
                "highlights": [{
                    "chunk_idx": None,
                    "text": fallback[1],
                    "sentence": fallback[1],
                    "score": None,
                    "word_start": fallback[0],
                    "word_end": _chunk_end(fallback[0], fallback[1]),
                    "matched_keywords": [],
                }],
            }

        # --- terugval / vrij zoekwoord: zin-gebaseerd -------------------------
        if q:
            keywords = [t.strip() for t in q.split() if len(t.strip()) > 1]
        else:
            keywords = _topic_keywords(con, topic_id)
            if not keywords:
                return {"error": "Topic niet gevonden"}

        sentences = re.split(r'(?<=[.!?])\s+', str(text))
        highlights, cursor = [], 0
        for s in sentences:
            kw_here = [kw for kw in keywords if kw.lower() in s.lower()]
            if kw_here:
                highlights.append({
                    "text": s, "sentence": s,
                    "start": cursor, "end": cursor + len(s),
                    "matched_keywords": kw_here,
                })
            cursor += len(s) + 1

        return {
            "iso": iso, "year": year, "topic": int(topic_id), "mode": "keyword",
            "keywords": keywords,
            "total_sentences": len(sentences),
            "highlighted_sentences": len(highlights),
            "highlights": highlights,
        }
    finally:
        con.close()

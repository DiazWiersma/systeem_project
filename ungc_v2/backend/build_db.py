# build_db.py - bouwt backend/ungdc.db consistent op vanuit EEN bron van waarheid.
# ----------------------------------------------------------------------------
# Waarom deze herschrijving?
# De vorige database was half-gemigreerd: speeches.topic_final was al hertoegewezen
# door het chunk-/topicmodel (schone labels), maar de afgeleide tabellen
# (topics, topic_year, country_topic) waren NIET opnieuw opgebouwd. Daardoor:
#   - topics.count / topic_year / country_topic gaven nog oude tellingen
#     (bv. topic 0 = 545 i.p.v. 1215) en de RUWE BERTopic-labels
#     ("0_sustainable_climate_change_..."), terwijl speeches schone labels had.
#   - speech_topics bevatte maar 1 topic per speech (rank 1) -> de feature
#     "meerdere topics per speech" deed in de praktijk niets.
#
# Dit script lost dat op: ALLE labels komen uit topic_table.csv en ALLE tellingen
# worden uit dezelfde brontabellen (speeches + chunk_topics_new) afgeleid, zodat
# de topiclijst, de choropleth, de timeline en de landenpanelen onderling kloppen.
#
# Chunkmodel: speeches worden in chunks van 150 woorden (overlap 30) geknipt en
# elke chunk krijgt een of meer topics. Dat zit in de tabel chunk_topics_new.
#   - Staat ungdc_topics.parquet / chunk_topics_new al klaar (uit better_topics.ipynb
#     met sentence-transformers), dan wordt DIE gebruikt.
#   - Anders bouwt dit script een lexicale stand-in op basis van topic_keywords.json,
#     zodat de app meteen draait. Vervang die later door de echte embeddings.
# ----------------------------------------------------------------------------

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent          # = backend/
DATA_DIR = BASE_DIR.parent / "data"       # = data/
DB_PATH  = BASE_DIR / "ungdc.db"          # = backend/ungdc.db

# Chunkparameters: MOETEN gelijk zijn aan die in better_topics.ipynb, anders
# kloppen de chunk-indexen van chunk_topics_new niet met de highlight-endpoint.
WORDS_PER_CHUNK = 150
OVERLAP = 30
TOP_K_PER_CHUNK = 2          # max topics per chunk
LEXICAL_MIN_SCORE = 1.5      # minimale (idf-gewogen) chunkscore voor een topic
LEXICAL_DOMINANCE = 1.4      # 2e topic alleen als hij in de buurt van de 1e komt
MIN_CHUNKS_PER_TOPIC = 2     # een topic telt pas als speech-topic bij >=2 chunks
MAX_TOPICS_PER_SPEECH = 6    # bovengrens aan topics per speech (rank 1 altijd erbij)

# TF-IDF stand-in (volledig offline): per chunk de best passende topic(s) op
# basis van cosine-similariteit tussen de chunk en de topic-omschrijving (+
# keywords). Dit kijkt naar de hele chunk/zin i.p.v. losse trefwoorden -- in
# dezelfde geest als de sentence-transformer-aanpak, maar zonder model-download.
TFIDF_MIN_SIM = 0.10         # minimale cosine om een chunk aan een topic te koppelen
TFIDF_DOMINANCE = 0.72       # 2e topic alleen als sim2 >= 0.72 * sim1

# Behoud het bestaande, door het echte model toegekende hoofdtopic per speech.
# Zet op False als je het hoofdtopic uit chunk_topics_new wilt herleiden (zoals
# de notebook doet: meeste chunks -> hoofdtopic).
PRESERVE_EXISTING_MAIN_TOPIC = True


def chunk_text(text, words_per_chunk=WORDS_PER_CHUNK, overlap=OVERLAP):
    """Identiek aan de chunking in better_topics.ipynb."""
    words = str(text).split()
    chunks, start = [], 0
    while start < len(words):
        end = start + words_per_chunk
        chunks.append(" ".join(words[start:end]))
        start += words_per_chunk - overlap
        if end >= len(words):
            break
    return chunks


def load_topic_table():
    """topic_table.csv = bron van waarheid voor topic-id -> schoon label + omschrijving."""
    p = DATA_DIR / "topic_table.csv"
    if not p.exists():
        return {}, {}
    df = pd.read_csv(p)
    label = dict(zip(df["topic_final"].astype(int), df["New label (suggested)"].astype(str)))
    desc_col = "Short description (for embeddings / app)"
    desc = dict(zip(df["topic_final"].astype(int),
                    df[desc_col].astype(str))) if desc_col in df.columns else {}
    return label, desc


def load_keywords():
    """topic_keywords.json -> {topic_id: [keywords]} voor de lexicale stand-in."""
    p = DATA_DIR / "topic_keywords.json"
    if not p.exists():
        return {}
    raw = json.load(open(p, encoding="utf-8"))
    return {int(k): v.get("keywords", []) for k, v in raw.items()}


def build_chunk_topics_lexical(conn, cur, speeches, label_of, kw_of):
    """Eenvoudige terugval als sklearn ontbreekt: idf-gewogen trefwoordtelling
    per chunk. Specifieke keywords ('apartheid', 'covid') wegen zwaar, generieke
    ('human', 'rights') licht, zodat niet elke chunk aan tien topics hangt."""
    import math
    import re as _re
    df_count = defaultdict(int)
    for terms in kw_of.values():
        for k in set(t.lower() for t in terms):
            df_count[k] += 1
    n_topics = max(len(kw_of), 1)
    weight = {k: math.log(1 + n_topics / c) for k, c in df_count.items()}
    topic_unigrams, topic_bigrams = {}, {}
    for t, terms in kw_of.items():
        uni, bi = [], []
        for k in terms:
            kl = k.lower().strip()
            (bi if " " in kl else uni).append(kl)
        topic_unigrams[t] = uni
        topic_bigrams[t] = bi

    cur.execute("DROP TABLE IF EXISTS chunk_topics_new")
    cur.execute("""CREATE TABLE chunk_topics_new
                   (speech_id INTEGER, chunk_idx INTEGER, topic_final INTEGER,
                    topic_label TEXT, score REAL)""")
    rows = []
    word_re = _re.compile(r"[a-z']+")
    LEXICAL_MIN_SCORE, LEXICAL_DOMINANCE = 1.5, 1.4
    for r in speeches.itertuples(index=False):
        for ci, chunk in enumerate(chunk_text(r.text)):
            low = chunk.lower()
            wc = defaultdict(int)
            for w in word_re.findall(low):
                wc[w] += 1
            scored = []
            for t in kw_of:
                s = 0.0
                for kw in topic_unigrams[t]:
                    if wc.get(kw):
                        s += weight.get(kw, 1.0) * wc[kw]
                for kw in topic_bigrams[t]:
                    c = low.count(kw)
                    if c:
                        s += weight.get(kw, 1.5) * c
                if s >= LEXICAL_MIN_SCORE:
                    scored.append((s, t))
            if not scored:
                continue
            scored.sort(reverse=True)
            top = [scored[0]]
            if len(scored) > 1 and scored[1][0] * LEXICAL_DOMINANCE >= scored[0][0]:
                top.append(scored[1])
            top = top[:TOP_K_PER_CHUNK]
            maxs = top[0][0]
            for s, t in top:
                rows.append((int(r.speech_id), ci, int(t),
                             label_of.get(t, str(t)), round(s / maxs, 4)))
    cur.executemany("INSERT INTO chunk_topics_new VALUES (?,?,?,?,?)", rows)
    conn.commit()
    print(f"chunk_topics_new (lexicale stand-in): {len(rows)} rijen")


def build_chunk_topics_tfidf(conn, cur, speeches, label_of, desc_of, kw_of):
    """Bouwt chunk_topics_new met TF-IDF + cosine-similariteit.

    Per chunk (150 woorden, overlap 30) wordt de cosine berekend tussen de
    chunk en elk topicdocument (de schone omschrijving + keywords). De
    best passende topic(s) worden bewaard. Dit beoordeelt de hele chunk/zin
    i.p.v. losse trefwoorden -- in dezelfde geest als de
    sentence-transformer-aanpak uit better_topics.ipynb, maar volledig offline.

    Zodra de echte embeddings (chunk_topics_new of ungdc_topics.parquet uit de
    notebook) klaarstaan, gebruikt main() die en wordt deze functie overgeslagen.
    """
    from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer

    # 1) topicdocument = omschrijving + keywords (keywords iets zwaarder gewogen).
    topic_ids = sorted(set(label_of) | set(kw_of) | set(desc_of))
    topic_docs = []
    for t in topic_ids:
        desc = desc_of.get(t, "") or label_of.get(t, "")
        kws = " ".join(kw_of.get(t, []))
        topic_docs.append(desc + " " + (kws + " ") * 2)

    # 2) alle chunks verzamelen, met hun (speech_id, chunk_idx).
    chunk_meta, chunk_docs = [], []
    for r in speeches.itertuples(index=False):
        for ci, chunk in enumerate(chunk_text(r.text)):
            chunk_meta.append((int(r.speech_id), ci))
            chunk_docs.append(chunk)

    # 3) Hashing + genormaliseerde sublineaire TF (vaste, lage geheugenvoetafdruk;
    #    L2 -> dot == cosine). Bewust GEEN idf: dit corpus bestaat volledig uit
    #    VN-toespraken, dus juist de thematische woorden ('climate', 'development',
    #    'peace') komen overal voor; idf zou ze wegdrukken en de topictreffers
    #    verzwakken. Zonder idf houden die woorden hun gewicht.
    hv = HashingVectorizer(n_features=2 ** 18, alternate_sign=False,
                           ngram_range=(1, 2), stop_words="english", norm=None)
    counts = hv.transform(chunk_docs + topic_docs)
    X = TfidfTransformer(use_idf=False, sublinear_tf=True).fit_transform(counts)   # norm='l2'
    n = len(chunk_docs)
    CX = X[:n]
    TXt = X[n:].T.tocsr()        # (features x n_topics)

    cur.execute("DROP TABLE IF EXISTS chunk_topics_new")
    cur.execute("""CREATE TABLE chunk_topics_new
                   (speech_id INTEGER, chunk_idx INTEGER, topic_final INTEGER,
                    topic_label TEXT, score REAL)""")
    rows = []
    BATCH = 20000
    for b0 in range(0, n, BATCH):
        b1 = min(b0 + BATCH, n)
        sims = (CX[b0:b1] @ TXt).toarray()            # (B x n_topics) cosine
        for i in range(b1 - b0):
            row = sims[i]
            j1 = int(row.argmax())
            best = float(row[j1])
            if best < TFIDF_MIN_SIM:
                continue
            sid, ci = chunk_meta[b0 + i]
            picks = [(best, j1)]
            row[j1] = -1.0
            j2 = int(row.argmax())
            s2 = float(row[j2])
            if s2 >= TFIDF_MIN_SIM and s2 >= TFIDF_DOMINANCE * best:
                picks.append((s2, j2))
            for s, j in picks[:TOP_K_PER_CHUNK]:
                t = topic_ids[j]
                rows.append((sid, ci, int(t), label_of.get(t, str(t)),
                             round(s / best, 4)))
    cur.executemany("INSERT INTO chunk_topics_new VALUES (?,?,?,?,?)", rows)
    conn.commit()
    print(f"chunk_topics_new (TF-IDF stand-in): {len(rows)} rijen over {n} chunks")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # --- 0) speeches: uit bestaande DB houden, of (her)laden uit parquet -------
    clean_path = DATA_DIR / "ungdc_clean.parquet"
    have_speeches = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='speeches'"
    ).fetchone() is not None
    if clean_path.exists():
        df = pd.read_parquet(clean_path)
        df.to_sql("speeches", conn, if_exists="replace", index=False)
        print(f"speeches herladen uit parquet: {len(df)} rijen")
    elif have_speeches:
        print("speeches: bestaande tabel hergebruikt (geen parquet aanwezig)")
    else:
        raise SystemExit("Geen speeches-tabel en geen ungdc_clean.parquet gevonden.")

    label_of, desc_of = load_topic_table()
    kw_of = load_keywords()
    if not label_of:
        print("LET OP: topic_table.csv niet gevonden -> labels uit speeches gebruikt.")

    speeches = pd.read_sql(
        "SELECT rowid AS speech_id, iso, year, country_clean, topic_final, "
        "topic_final_name, text FROM speeches", conn)

    # --- 1) chunk_topics_new -------------------------------------------------
    chunk_exists = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunk_topics_new'"
    ).fetchone() is not None
    topics_parquet = DATA_DIR / "ungdc_topics.parquet"

    if chunk_exists:
        print("chunk_topics_new bestaat al -> gebruikt zoals die is (echte embeddings).")
    elif topics_parquet.exists():
        tp = pd.read_parquet(topics_parquet)
        tp.to_sql("chunk_topics_new", conn, if_exists="replace", index=False)
        print(f"chunk_topics_new geladen uit parquet: {len(tp)} rijen")
        chunk_exists = True
    else:
        print("Geen echte chunk-data -> stand-in opbouwen "
              "(vervang later door better_topics.ipynb met echte embeddings).")
        try:
            build_chunk_topics_tfidf(conn, cur, speeches, label_of, desc_of, kw_of)
        except Exception as e:
            print(f"TF-IDF niet beschikbaar ({e}) -> eenvoudige lexicale terugval.")
            build_chunk_topics_lexical(conn, cur, speeches, label_of, kw_of)
        chunk_exists = True

    # --- 2) hoofdtopic per speech -------------------------------------------
    # n_chunks per (speech, topic) uit chunk_topics_new
    ct = pd.read_sql(
        "SELECT speech_id, topic_final AS topic, COUNT(*) AS n_chunks, "
        "AVG(score) AS avg_score FROM chunk_topics_new GROUP BY speech_id, topic_final",
        conn)

    main_topic = {}   # speech_id -> topic
    if PRESERVE_EXISTING_MAIN_TOPIC:
        for r in speeches.itertuples(index=False):
            if r.topic_final is not None and int(r.topic_final) != -1:
                main_topic[int(r.speech_id)] = int(r.topic_final)
    if not main_topic or not PRESERVE_EXISTING_MAIN_TOPIC:
        # hoofdtopic = topic met de meeste chunks (notebook-logica)
        best = (ct.sort_values(["speech_id", "n_chunks", "avg_score"],
                               ascending=[True, False, False])
                  .groupby("speech_id").first().reset_index())
        for r in best.itertuples(index=False):
            main_topic.setdefault(int(r.speech_id), int(r.topic))

    sid_meta = {int(r.speech_id): (r.iso, int(r.year), r.country_clean)
                for r in speeches.itertuples(index=False)}

    # speeches.topic_final / topic_final_name bijwerken naar het schone label
    for sid, t in main_topic.items():
        iso, year, _ = sid_meta[sid]
        cur.execute("UPDATE speeches SET topic_final=?, topic_final_name=? "
                    "WHERE iso=? AND year=?",
                    (t, label_of.get(t, str(t)), iso, year))
    conn.commit()

    # --- 3) speech_topics: MEERDERE topics per speech ------------------------
    # rank 1 = hoofdtopic; daarna de overige chunk-topics op aflopend n_chunks.
    nchunks = defaultdict(dict)   # speech_id -> {topic: n_chunks}
    for r in ct.itertuples(index=False):
        nchunks[int(r.speech_id)][int(r.topic)] = int(r.n_chunks)

    cur.execute("DROP TABLE IF EXISTS speech_topics")
    cur.execute("""CREATE TABLE speech_topics
                   (iso TEXT, year INTEGER, topic INTEGER, topic_label TEXT, rank INTEGER)""")
    st_rows = []
    for sid, (iso, year, _) in sid_meta.items():
        main_t = main_topic.get(sid)
        if main_t is None:
            continue
        # alleen topics die in genoeg chunks terugkomen tellen als bijtopic
        others = sorted(
            (t for t, n in nchunks.get(sid, {}).items()
             if t != main_t and n >= MIN_CHUNKS_PER_TOPIC),
            key=lambda t: nchunks[sid][t], reverse=True)
        ordered = [main_t] + others[:MAX_TOPICS_PER_SPEECH - 1]
        for rank, t in enumerate(ordered, start=1):
            st_rows.append((iso, year, int(t), label_of.get(t, str(t)), rank))
    cur.executemany("INSERT INTO speech_topics VALUES (?,?,?,?,?)", st_rows)
    conn.commit()
    print(f"speech_topics: {len(st_rows)} rijen "
          f"({len(st_rows)/max(len(sid_meta),1):.2f} topics per speech gemiddeld)")

    # --- 4) afgeleide tabellen, allemaal uit speech_topics (multi-topic) -----
    # Definitie: een speech telt mee voor ELK topic dat hij aanraakt. Zo zijn
    # /topics, /map, /timeline en /country-topics onderling consistent.
    st = pd.read_sql("SELECT iso, year, topic FROM speech_topics", conn)
    cmeta = (speeches[["iso", "year", "country_clean"]]
             .drop_duplicates().rename(columns={"country_clean": "country"}))
    st = st.merge(cmeta, on=["iso", "year"], how="left")

    def lab(t):
        return label_of.get(int(t), str(t))

    # topics
    topics = (st.groupby("topic").size().reset_index(name="count"))
    # zorg dat ALLE 97 topics erin staan (ook met count 0)
    all_topics = sorted(set(label_of) | set(topics["topic"]))
    tcount = dict(zip(topics["topic"], topics["count"]))
    cur.execute("DROP TABLE IF EXISTS topics")
    cur.execute("CREATE TABLE topics (topic INTEGER, topic_label TEXT, count INTEGER)")
    cur.executemany("INSERT INTO topics VALUES (?,?,?)",
                    [(int(t), lab(t), int(tcount.get(t, 0))) for t in all_topics])

    # topic_year
    total_year = st.groupby("year")["topic"].count().to_dict()  # tel per jaar (multi)
    ty = st.groupby(["year", "topic"]).size().reset_index(name="count")
    cur.execute("DROP TABLE IF EXISTS topic_year")
    cur.execute("""CREATE TABLE topic_year
                   (year INTEGER, topic INTEGER, topic_label TEXT,
                    count INTEGER, total_speeches INTEGER, share REAL)""")
    cur.executemany("INSERT INTO topic_year VALUES (?,?,?,?,?,?)",
                    [(int(r.year), int(r.topic), lab(r.topic), int(r["count"]),
                      int(total_year[r.year]),
                      round(r["count"] / total_year[r.year], 6))
                     for _, r in ty.iterrows()])

    # country_topic (geen dubbele rijen meer)
    total_country = st.groupby("iso")["topic"].count().to_dict()
    country_name = dict(zip(cmeta["iso"], cmeta["country"]))
    cty = st.groupby(["iso", "topic"]).size().reset_index(name="count")
    cur.execute("DROP TABLE IF EXISTS country_topic")
    cur.execute("""CREATE TABLE country_topic
                   (iso TEXT, country TEXT, topic INTEGER, topic_label TEXT,
                    count INTEGER, total_speeches INTEGER, share REAL)""")
    cur.executemany("INSERT INTO country_topic VALUES (?,?,?,?,?,?,?)",
                    [(r.iso, country_name.get(r.iso, r.iso), int(r.topic), lab(r.topic),
                      int(r["count"]), int(total_country[r.iso]),
                      round(r["count"] / total_country[r.iso], 6))
                     for _, r in cty.iterrows()])
    conn.commit()

    # --- 4b) topic_meta: label + omschrijving + keywords, zodat de frontend
    #         deze details live uit de database kan halen i.p.v. uit een grote
    #         ingebedde CSV. count komt mee voor het gemak. ---------------------
    cur.execute("DROP TABLE IF EXISTS topic_meta")
    cur.execute("""CREATE TABLE topic_meta
                   (topic INTEGER, topic_label TEXT, description TEXT,
                    keywords TEXT, count INTEGER)""")
    cur.executemany("INSERT INTO topic_meta VALUES (?,?,?,?,?)",
                    [(int(t), lab(t), str(desc_of.get(t, "")),
                      ", ".join(kw_of.get(t, [])), int(tcount.get(t, 0)))
                     for t in all_topics])
    conn.commit()

    # --- 5) indexen ----------------------------------------------------------
    for stmt in [
        "CREATE INDEX IF NOT EXISTS idx_iso ON speeches(iso)",
        "CREATE INDEX IF NOT EXISTS idx_topic ON speeches(topic_final)",
        "CREATE INDEX IF NOT EXISTS idx_year ON speeches(year)",
        "CREATE INDEX IF NOT EXISTS idx_sp_iso_year ON speeches(iso, year)",
        "CREATE INDEX IF NOT EXISTS idx_st_iso_year ON speech_topics(iso, year)",
        "CREATE INDEX IF NOT EXISTS idx_st_topic ON speech_topics(topic)",
        "CREATE INDEX IF NOT EXISTS idx_ct_chunk ON chunk_topics_new(speech_id, topic_final)",
    ]:
        cur.execute(stmt)
    conn.commit()
    conn.close()
    print("Database consistent opgebouwd.")


if __name__ == "__main__":
    main()

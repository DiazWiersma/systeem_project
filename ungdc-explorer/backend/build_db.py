import pandas as pd
import sqlite3
from pathlib import Path

# Paden relatief aan dit script
BASE_DIR = Path(__file__).parent          # = backend/
DATA_DIR = BASE_DIR.parent / "data"       # = data/
DB_PATH  = BASE_DIR / "ungdc.db"          # = backend/ungdc.db

conn = sqlite3.connect(DB_PATH)

df = pd.read_parquet(DATA_DIR / "ungdc_clean.parquet")
df.to_sql("speeches", conn, if_exists="replace", index=False)

topics = pd.read_csv(DATA_DIR / "topic_counts.csv")
topics.to_sql("topics", conn, if_exists="replace", index=False)

tyd = pd.read_csv(DATA_DIR / "topic_year_distribution.csv")
tyd.to_sql("topic_year", conn, if_exists="replace", index=False)

ctd = pd.read_csv(DATA_DIR / "country_topic_distribution.csv")
ctd.to_sql("country_topic", conn, if_exists="replace", index=False)

conn.execute("CREATE INDEX IF NOT EXISTS idx_iso ON speeches(iso)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON speeches(topic_final)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_year ON speeches(year)")
conn.commit()
conn.close()
print("Database aangemaakt.")
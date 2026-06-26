#!/usr/bin/env python3

import sys
import os
import time
import threading
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent

BACKEND = HERE / "backend" if (HERE / "backend" / "main.py").exists() else HERE

sys.path.insert(0, str(BACKEND))
import uvicorn
from fastapi.staticfiles import StaticFiles
import main

app = main.app

candidates = [HERE / "ungc.html", HERE / "frontend" / "ungc.html", HERE / "backend" / "ungc.html"]
site_dir = next((p.parent for p in candidates if p.exists()), HERE)
if not (site_dir / "ungc.html").exists():
    print("Let op: ungc.html niet gevonden. Zet 'm naast run.py (of in de map frontend).")
app.mount("/app", StaticFiles(directory=str(site_dir), html=True), name="site")

URL = "http://localhost:8000/app/ungc.html"


def open_browser():
    time.sleep(2)
    webbrowser.open(URL)


if os.environ.get("UNGC_NO_BROWSER") != "1":
    threading.Thread(target=open_browser, daemon=True).start()

print("\n  UNGC Explorer draait op:  " + URL)
print("  Stoppen? Sluit dit venster of druk op Ctrl+C.\n")

uvicorn.run(app, host="127.0.0.1", port=8000)

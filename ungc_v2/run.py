#!/usr/bin/env python3
# run.py - start de backend EN open de website in 1 keer.
# Dit bestand laat main.py helemaal met rust; het importeert alleen de bestaande app
# en serveert ungc.html erbij, zodat de site en de API op hetzelfde adres draaien.
#
# Gebruik: zet dit bestand + ungc.html naast de map "backend" en start het
# (dubbelklik start.command op Mac of start.bat op Windows, of: python3 run.py).

import sys
import time
import threading
import webbrowser
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent

# zoek de map met main.py (meestal ./backend, anders deze map zelf)
BACKEND = HERE / "backend" if (HERE / "backend" / "main.py").exists() else HERE

# de pakketten die de backend nodig heeft; installeer ze als ze nog missen
try:
    import fastapi  # noqa: F401
    import uvicorn  # noqa: F401
    import pandas   # noqa: F401
except ImportError:
    print("Even de benodigde pakketten installeren (1e keer)...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "fastapi", "uvicorn", "pandas"])

# nu pas de backend importeren (main.py blijft ongewijzigd)
sys.path.insert(0, str(BACKEND))
import uvicorn
from fastapi.staticfiles import StaticFiles
import main

app = main.app

# zoek waar ungc.html staat (hoofdmap, frontend/ of backend/) en serveer die map op /app,
# zodat de site en de API op hetzelfde adres draaien -> geen file://- of CORS-gedoe
candidates = [HERE / "ungc.html", HERE / "frontend" / "ungc.html", HERE / "backend" / "ungc.html"]
site_dir = next((p.parent for p in candidates if p.exists()), HERE)
if not (site_dir / "ungc.html").exists():
    print("Let op: ungc.html niet gevonden. Zet 'm naast run.py (of in de map frontend).")
app.mount("/app", StaticFiles(directory=str(site_dir), html=True), name="site")

URL = "http://localhost:8000/app/ungc.html"


def open_browser():
    time.sleep(2)          # geef de server heel even de tijd
    webbrowser.open(URL)


threading.Thread(target=open_browser, daemon=True).start()

print("\n  UNGC Explorer draait op:  " + URL)
print("  Stoppen? Sluit dit venster of druk op Ctrl+C.\n")

uvicorn.run(app, host="127.0.0.1", port=8000)

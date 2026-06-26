# UNGC Explorer

UNGC Explorer is een interactieve webapp voor het verkennen van United Nations General Debate speeches van 1946 tot en met 2025. De applicatie combineert een FastAPI-backend, een SQLite-database en een frontend met een interactieve wereldkaart.

## Vereisten

- Python 3.10 of hoger
- Git
- Git LFS, omdat de SQLite-database als groot bestand in de repository staat

Controleer of Git LFS actief is:

```bash
git lfs install
```

## Repository clonen

```bash
git clone <repository-url>
cd systeem_project
git lfs pull
```

Controleer daarna of de database echt is binnengehaald:

```bash
ls -lh backend/ungdc.db
```

Op Windows PowerShell:

```powershell
Get-Item backend\ungdc.db
```

De database hoort ongeveer 296 MB te zijn. Als het bestand maar een paar bytes groot is, is alleen de Git LFS pointer aanwezig. Voer dan opnieuw uit:

```bash
git lfs pull
```

## Installatie

Maak een virtuele Python-omgeving aan en installeer de benodigde packages.

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

## App starten

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe run.py
```

Of dubbelklik op:

```text
start.bat
```

macOS/Linux:

```bash
python run.py
```

De app draait daarna op:

```text
http://localhost:8000/app/ungc.html
```

## Projectstructuur

```text
backend/
  main.py                  FastAPI-backend
  requirements.txt         Python-dependencies voor de app
  ungdc.db                 SQLite-database

frontend/
  ungc.html                Hoofdpagina
  ungc.css                 Styling
  ungc.js                  Interactieve kaart en frontend-logica
  un_logo.svg              Logo
  favicon.ico              Browsericoon

run.py                     Start backend en serveert de frontend
start.bat                  Windows-startbestand
```

## Problemen oplossen

Als `python` of `py` niet wordt herkend, installeer Python via https://www.python.org/downloads/ en vink tijdens installatie "Add Python to PATH" aan.

Als dependencies ontbreken:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Als de database niet wordt gevonden of niet werkt, controleer of Git LFS de database heeft binnengehaald:

```bash
git lfs pull
```

Als poort 8000 al in gebruik is, sluit het oude terminalvenster waarin de app draait en start opnieuw.

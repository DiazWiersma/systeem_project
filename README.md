# systeem_project# 📦 Handleiding: Repository clonen met grote bestanden (Git LFS)

Deze repository maakt gebruik van **Git LFS (Large File Storage)** voor grote bestanden zoals `.db` en `.parquet` bestanden. Volg onderstaande stappen om de repository correct te clonen.

---

## Vereisten

- [Git](https://git-scm.com/downloads) geïnstalleerd
- [Git LFS](https://git-lfs.com) geïnstalleerd

---

## Stap 1 — Installeer Git LFS

| Besturingssysteem | Commando |
|---|---|
| **Windows** | Download via [git-lfs.com](https://git-lfs.com) of `winget install GitHub.GitLFS` |
| **macOS** | `brew install git-lfs` |
| **Linux** | `sudo apt install git-lfs` |

Activeer daarna Git LFS eenmalig op je systeem:

```bash
git lfs install
```

---

## Stap 2 — Clone de repository

```bash
git clone https://github.com/jouw-org/jouw-repo.git
```

De grote bestanden worden automatisch meegedownload.

---

## Stap 3 — Controleer of het gelukt is

```bash
git lfs ls-files
```

De grote bestanden (`.db`, `.parquet`) moeten hier zichtbaar zijn. Controleer ook of de bestandsgroottes kloppen:

```bash
ls -lh pad/naar/bestand.db
```

> ⚠️ Als een bestand slechts ~130 bytes groot is, is alleen de **pointer** gedownload en niet het echte bestand. Voer dan het volgende uit:
> ```bash
> git lfs pull
> ```

---

## Problemen?

Neem contact op met de beheerder van de repository.
# Data provenance - UNGC Explorer

Dit bestand beschrijft hoe de huidige data voor de UNGC Explorer tot stand is gekomen
en hoe de applicatie die data gebruikt.

## Huidige databron voor de app

De draaiende applicatie gebruikt een SQLite-database:

`backend/ungdc.db`

De frontend leest geen losse CSV-bestanden meer voor de interactieve data. Alle
informatie die de kaart, filters, topiclijst, speeches en highlights nodig hebben,
komt via de FastAPI-backend uit deze database.

Belangrijke API-routes:

- `/status` - controleert databasebereik en algemene aantallen.
- `/topics/details` - levert topicnamen, omschrijvingen, keywords en aantallen.
- `/map` - levert kaartaggregatie per land.
- `/speeches` - levert speeches op basis van land, topic, periode en zoekwoord.
- `/timeline` - levert tijdreeksen per topic en optioneel per land.
- `/country-topics/{iso}` - levert topicverdeling per land.
- `/speech/{iso}/{year}` - levert de volledige speech.
- `/speech/{iso}/{year}/highlights` - levert relevante tekstfragmenten.

## Oorspronkelijke brondata

De basis is de United Nations General Debate Corpus (UNGDC), versie 14
van maart 2026. Deze versie bevat de periode 1946-2025, inclusief Session 80
uit 2025.

Volgens de meegeleverde bron-README bevat de dataset:

- UN General Debate speeches van 1946 tot en met 2025.
- Plain text speeches in UTF-8.
- Bestandsnamen volgens het patroon:
  `ISO_SESSION_YEAR.txt`, bijvoorbeeld `USA_75_2020.txt`.
- 2025 is methodologisch anders verwerkt: omdat gevalideerde PDF-transcripten
  voor Session 80 nog niet beschikbaar waren, is die sessie opgebouwd uit
  officiele simultaanvertolking-audio en transcriptie.
- 2024 is deels opgebouwd uit officiële web/PDF-bronnen, OCR en vertaling waar
  nodig.

Te citeren bronnen bij gebruik van de UNGDC-data:

- Jankin, S., Baturo, A., & Dasandi, N. (2025). *Words to unite nations: The
  complete United Nations General Debate Corpus, 1946-present*. Journal of
  Peace Research, 62(4), 1339-1351.
- Alexander Baturo, Niheer Dasandi, and Slava Mikhaylov (2017).
  *Understanding State Preferences With Text As Data: Introducing the UN
  General Debate Corpus*. Research & Politics.

## Verwerking richting de huidige database

De huidige database is gebaseerd op de v2-versie van het project. In die versie
zijn de ruwe speeches opgeschoond, gekoppeld aan metadata en voorzien van
topicinformatie.

De globale verwerkingsstappen waren:

1. Ruwe UNGDC-tekstbestanden en metadata zijn omgezet naar een opgeschoonde
   speeches-tabel.
2. Speeches zijn in tekstchunks van 150 woorden met 30 woorden overlap verdeeld.
3. Chunks zijn gekoppeld aan topiclabels. Daardoor kan een speech meerdere
   topics hebben, in plaats van slechts een enkel hoofdtopic.
4. Topiclabels, beschrijvingen en keywords zijn opgeschoond tot leesbare labels
   voor de app.
5. Afgeleide tabellen zijn opnieuw opgebouwd uit dezelfde bronlogica, zodat
   topiclijst, kaart, timeline en landpanelen dezelfde tellingen gebruiken.
6. Alles is samengebracht in `backend/ungdc.db`.

Voor de draaiende app is `backend/ungdc.db` de centrale bron. De losse
bronbestanden en oude notebooks zijn bewust niet meer nodig in deze map; ze
zouden alleen gebruikt worden wanneer de database volledig opnieuw opgebouwd
moet worden vanuit de oorspronkelijke dataset.

## Huidige database-inhoud

De huidige `backend/ungdc.db` bevat:

- `speeches`: 11.127 speeches.
- `topics`: 97 topics.
- `topic_meta`: 97 topicbeschrijvingen met keywords.
- `speech_topics`: 33.932 speech-topickoppelingen.
- `chunk_topics_new`: 142.063 chunk-topickoppelingen.
- `topic_year`: 5.330 topic-jaaraggregaties.
- `country_topic`: 7.242 land-topicaggregaties.

Dekking:

- Jaren: 1946-2025.
- Landcodes in speeches: 199.
- Multi-topic ondersteuning: aanwezig via `speech_topics`.

## Waarom de API leidend is

In eerdere versies stonden topicgegevens ook als losse of ingebedde CSV in de
frontend. Dat gaf risico op verschillen tussen wat de database telde en wat de
website liet zien.

In de huidige opzet is de API leidend:

- De topiclijst komt uit `/topics/details`.
- De kaartkleuren komen uit `/map`.
- Landpanelen en speechfragmenten komen uit `/speeches` en `/highlights`.
- De frontend hoeft geen losse topic-CSV meer te vertrouwen.

Hierdoor is er een centrale bron van waarheid: `backend/ungdc.db`.

## Bestanden die cruciaal zijn voor de app

Minimale runtime-bestanden:

- `run.py`
- `start.bat`
- `start.command`
- `backend/main.py`
- `backend/requirements.txt`
- `backend/ungdc.db`
- `frontend/ungc.html`
- `frontend/ungc.css`

Nuttig voor verantwoording:

- `DATA_PROVENANCE.md`

Losse CSV/parquet/json-bronbestanden zijn verwijderd uit de runtime-map. De app
hoort ze niet direct te gebruiken.

# Deep Dive-kit: validatieframework voor LLM-herschreven SELECT-query's

Scope: alleen **herschrijven van SELECT-query's**. Geen indexen, geen schemawijzigingen, geen applicatiecode.
Schema-informatie mag later wel als leesbare context aan een model worden meegegeven.

Wat dit is: een eerste versie (dag 1) van het meetinstrument. Het controleert of een kandidaat-query
(1) een enkele toegestane SELECT is, (2) in een read-only transactie draait, (3) dezelfde resultaten geeft als het origineel
op meerdere parametersets, en (4) aantoonbaar sneller is (mediaan van herhaalde, afwisselende metingen).
Met bewust foute herschrijvingen ("mutanten") meet je daarna hoe betrouwbaar het framework zelf is.

## Wat getest is en wat niet

- Getest: Linux (Python 3.12), PostgreSQL 16.2 via `pgserver`, SUE-repo commit 6951dfc, schaal 0.02, seed 42.
- NIET getest: Windows, andere Python-versies, andere schalen dan 0.02 en 0.05.
- De labels `expected` in `cases/cases.py` zijn de redenering van de auteur van de kit en zijn dus zelf een aanname.
- Tijdmetingen: standaardinstellingen van PostgreSQL, niet de bewust slechte `postgresql.conf` van SUE. Niet vergelijkbaar met SUE's baseline.
- `pg_stat_statements` en `auto_explain` zitten niet in `pgserver`. De kit gebruikt ze niet.

## Hoe het in elkaar zit: twee mappen, een omgeving

1. **SUE-repo (kopie)**: levert het databaseschema (migraties) en de dataset-generator. Hier draai je alleen `alembic` en `seed.generate`.
2. **Deze kit (`deepdive_kit`)**: het validatieframework. Hier draai je `start_db`, `run_validation` en `stop_db`.

Beide gebruiken dezelfde Python-omgeving (conda, Python 3.12). Je hoeft de SUE-code niet aan te passen, behalve een regel in een kopie (stap 4).

## Installeren (Windows/PyCharm/conda; op Linux getest, op Windows nog niet)

Gebruik de terminal onderin PyCharm (op Windows meestal PowerShell) of de Anaconda Prompt.

1. Omgeving: `conda create -n deepdive python=3.12 -y`, daarna `conda activate deepdive`. Het moet Python 3.12 zijn.
2. Pakketten: `pip install pgserver sqlglot "psycopg[binary]" "sqlalchemy>=2.0.30" "alembic>=1.13" "pydantic>=2.7" "pydantic-settings>=2.3" "structlog>=24.1" "faker>=25.0" "rich>=13.7" "typer>=0.12" "fastapi>=0.115"`
3. Maak een kopie van je gekloonde SUE-map, bijvoorbeeld `sql-performance-challenge-lab`, en werk daarin.
4. Open in die kopie `migrations/versions/0001_tenancy.py` en verwijder de regel `op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")`. (pgserver bevat pgcrypto niet; `gen_random_uuid()` zit in PostgreSQL zelf.) Noem dit in je verslag.
5. Start de database (vanuit de kit-map): `python scripts/start_db.py C:\pgdata\bazaar`. Het script print een URI. Kopieer die.
6. Ga naar de SUE-kopie. Zet de URI met `postgresql+psycopg://` in plaats van `postgresql://` in een omgevingsvariabele:
   PowerShell: `$env:BAZAAR_DATABASE_URL="postgresql+psycopg://..."` (rest van de URI behouden)
   cmd: `set BAZAAR_DATABASE_URL=postgresql+psycopg://...`
7. Migreren: `python -m alembic upgrade head`. Verwacht 25 keer "Running upgrade".
8. Data genereren: `python -m seed.generate --scale 0.02 --database-url "<URI van stap 5>" --manifest manifest.json`. Verwacht: "done in ..." na ongeveer 15 seconden en 757.396 rijen.
9. Ga terug naar de kit-map en draai: `python scripts/run_validation.py "<URI van stap 5>" --reps 5`. Duurt ongeveer 3 tot 5 minuten.
10. Controle: onderaan staat "Fout gedetecteerd: 14/15", "Foute afkeuringen: 0/4" en "Gemist: M3_geen_id_tiebreak". Een iets ander getal is een bevinding, geen fout van jou, maar vermeld het.
11. Stoppen: `python scripts/stop_db.py C:\pgdata\bazaar`

Let op: `top_customers` van SUE is bewust traag; gebruik schaal 0.02 (op 0.05 duurde een uitvoering 34 tot 56 seconden).

## Mapindeling

- `validator/classes.py`: datastructuren `Result` en `Comparison`
- `validator/checker.py`: statische controle (sqlglot), read-only uitvoering, resultaatvergelijking
- `validator/timing.py`: herhaalde, afwisselende tijdmeting (mediaan, IQR, versnelling, drempel 1,2)
- `validator/normalize.py`: waarden vergelijkbaar maken (int/Decimal/float, datum, json)
- `cases/classes.py`: datastructuren `Candidate` en `Case`
- `cases/cases.py`: 4 query's uit de repo, 4 gelijkwaardige herschrijvingen, 15 foute varianten (mutanten)
- `results/`: uitvoer van twee runs van de auteur op Linux (5 en 3 herhalingen), om de run-tot-run-variatie te zien

## Resultaat van de eerste run (schaal 0.02, 5 herhalingen)

Zie `results/`. In het kort: 14 van de 15 mutanten werden gedetecteerd, 0 van de 4 gelijkwaardige herschrijvingen werden onterecht afgekeurd.
De gemiste mutant (`M3_geen_id_tiebreak`) ontsnapt omdat in `audit_log` alle `(tenant_id, created_at)`-combinaties uniek zijn
(60.100 van 60.100), waardoor een ontbrekende tiebreak in deze data niets verandert.

## Volgende stappen (dag 2)

- LLM-aanroepen: 4 contextcondities per query, meerdere herhalingen, elke uitvoer door dit framework laten beoordelen.
- Een tweede dataset of parameterset met veel gelijke waarden (ties), om mutanten zoals `M3_geen_id_tiebreak` te kunnen vangen.
- Meetruis: dezelfde gelijkwaardige query meerdere keren meten om te zien hoe vaak "sneller" of "trager" alleen ruis is.

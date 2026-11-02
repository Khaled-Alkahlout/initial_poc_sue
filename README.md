# SQL Rewrite Validator

Een validatieframework dat controleert of een herschreven SQL-query (bijvoorbeeld door een LLM) **geldig, resultaat-gelijk en aantoonbaar sneller** is dan het origineel, plus een testbank om herschrijvingen op grote schaal te laten maken en beoordelen.

---

## Inleiding

### Het probleem

Een LLM kan een trage SQL-query herschrijven naar iets dat er sneller uitziet. Maar een herschrijving die er goed uitziet, is daarmee nog niet goed. Er zijn drie manieren waarop het misgaat:

- De herschrijving is **geen geldige of toegestane query** (bijvoorbeeld een `DELETE` in een CTE).
- De herschrijving geeft een **ander resultaat**. Een enkele verandering is genoeg, zoals een vervangen statuswaarde, een weggevallen filter of een andere sortering. Zo'n fout leest een mens snel over.
- De herschrijving geeft hetzelfde resultaat, maar is **niet sneller**, of zelfs trager.

### Wat deze repository doet

Deze repository beoordeelt elke herschrijving automatisch in drie stappen:

1. **Statische controle.** Is het precies één `SELECT`, zonder schrijfacties?
2. **Resultaatvergelijking.** Geeft de herschrijving op meerdere parametersets exact dezelfde rijen als het origineel?
3. **Tijdmeting.** Is de herschrijving op een eerlijke, herhaalde meting minstens 1,2× sneller?

Het eindoordeel is een van vier uitkomsten: `REJECTED_STATIC`, `REJECTED_NOT_EQUIVALENT`, `EQUIVALENT_NOT_FASTER` of `ACCEPTED`.

### Wat erin zit

| Onderdeel | Wat het is |
|---|---|
| **Validator** (`validator/`) | De drie controles hierboven, als losse, herbruikbare functies |
| **Testbank** (`cases/`) | Vier trage query's met parametersets en handgemaakte herschrijvingen met een bekend oordeel |
| **Mutatietest** (`scripts/run_validation.py`) | Laat de validator los op herschrijvingen waarvan het oordeel bekend is, om te meten of de validator zelf klopt |
| **LLM-koppeling** (`llm/`, `scripts/run_llm.py`) | Bouwt een prompt met een instelbare hoeveelheid context, roept een model aan en laat elk antwoord door de validator beoordelen |
| **A/A-controle** (`run_llm.py --model mock`) | Vergelijkt het origineel met zichzelf, om de meetruis en onterechte `ACCEPTED`-oordelen te meten |
| **Analyse** (`scripts/analyse.py`) | Zet de ruwe resultaten om in tabellen, betrouwbaarheidsintervallen, voorbeelden en figuren |
| **Database-hulp** (`scripts/start_db.py`, `stop_db.py`) | Start en stopt een ingebedde PostgreSQL 16, zodat er niets apart hoeft te worden geïnstalleerd |

### Waarvoor je het kunt gebruiken

- Een **herschrijving van een query controleren** voordat je hem toepast.
- Meten **hoe betrouwbaar een validator is**, voordat je erop vertrouwt.
- **Prompts of modellen vergelijken** door ze op dezelfde query's los te laten.
- Een **eigen query toevoegen** (zie [hoofdstuk 6](#6-een-eigen-query-toevoegen)).

### Scope

Alleen het herschrijven van `SELECT`-query's. Geen indexen, geen schemawijzigingen, geen applicatiecode. De validator werkt op PostgreSQL (sqlglot-dialect `postgres`).

De testdatabase is de webshop "Bazaar" van SUE (FastAPI, PostgreSQL 16, bewust traag). Die code zit niet in deze repository; [hoofdstuk 5](#5-installeren-en-draaien-stap-voor-stap) legt uit hoe je hem ophaalt.

---

## Inhoud

1. [Hoe het werkt](#1-hoe-het-werkt)
2. [De vier condities voor het model](#2-de-vier-condities-voor-het-model)
3. [Mapstructuur en bestanden](#3-mapstructuur-en-bestanden)
4. [Wat je nodig hebt](#4-wat-je-nodig-hebt)
5. [Installeren en draaien, stap voor stap](#5-installeren-en-draaien-stap-voor-stap)
6. [Een eigen query toevoegen](#6-een-eigen-query-toevoegen)
7. [Problemen oplossen](#7-problemen-oplossen)
8. [Technische beperkingen](#8-technische-beperkingen)
9. [Bronnen](#9-bronnen)

---

## 1. Hoe het werkt

```
 originele query ──► (LLM of handgemaakte kandidaat) ──► herschreven SQL ──► VALIDATIE ──► oordeel
                                                                              │
          1. statische controle (sqlglot)  ── niet geldig ──────────────► REJECTED_STATIC
          2. zelfde resultaat op alle parametersets ── verschil ───────► REJECTED_NOT_EQUIVALENT
          3. tijd: ABAB, mediaan ── speedup < 1,2 ─────────────────────► EQUIVALENT_NOT_FASTER
                                  ── speedup ≥ 1,2 ────────────────────► ACCEPTED
```

**Statische controle** (`validator/checker.py`, `static_check`). De SQL wordt geparsed met sqlglot (PostgreSQL-dialect). Het moet precies één `SELECT` zijn. DDL en DML worden afgekeurd, ook binnen een CTE.

**Resultaatvergelijking** (`checker.py`, `run_query` en `compare`). Elke query draait in een read-only transactie met een `statement_timeout`, die altijd wordt teruggedraaid. De rijen worden vergeleken als multiset van genormaliseerde waarden (`validator/normalize.py`: int, `Decimal` en float zijn gelijk bij dezelfde waarde). Heeft het origineel een `ORDER BY`, dan wordt ook de volgorde van de sorteersleutel vergeleken. Een verschil dat alleen rijen met dezelfde sorteersleutel aan de `LIMIT`-grens betreft, geeft `TIE_AMBIGUOUS` en telt niet als fout, omdat beide uitkomsten dan geldig zijn.

**Parametersets** (`cases/cases.py`, `make_ctx`). De parameters komen uit de database zelf: een grote en een kleine tenant (de tenants met de meeste en de minste orders), elk met vier tijdvensters:

| Venster | Doel |
|---|---|
| `full` | alle data |
| `recent` | de laatste 90 dagen |
| `empty` | een venster zonder data (vangt fouten bij lege uitkomsten) |
| `boundary` | bovengrens precies op de laatste order (laat `<` en `<=` verschillen) |

Een gelijk resultaat op één parameterset bewijst weinig; daarom worden alle combinaties gecontroleerd. Voor trage query's kan een deelverzameling worden gebruikt (zie `tc_params` in `cases.py`).

**Tijdmeting** (`validator/timing.py`, `measure`). Origineel en herschrijving worden om en om gemeten (ABAB), zodat een tijdelijk trage periode van de computer beide even hard raakt. Standaard zijn dat 2 warm-ups en 7 meetherhalingen; de **mediaan** telt, omdat één uitschieter de mediaan niet verandert. De speedup is de mediaan van het origineel gedeeld door die van de herschrijving, en pas vanaf `SPEEDUP_THRESHOLD = 1.2` is het oordeel `ACCEPTED`. Duurt het origineel langer dan 5 seconden, dan worden hooguit 3 herhalingen zonder warm-up gedaan.

**Mutatietest.** `cases/cases.py` bevat per query handgemaakte herschrijvingen met een verwacht oordeel (`expected`): foute (mutanten, gemaakt door kleine wijzigingen aan de SQL) en gelijkwaardige. De validator moet alle foute afkeuren en geen gelijkwaardige. Het verwachte oordeel is de redenering van degene die de herschrijving maakte en is niet onafhankelijk bewezen.

**A/A-controle.** `run_llm.py --model mock` geeft het origineel terug als "antwoord". De echte speedup is dan 1,0, dus elke `ACCEPTED` is meetruis.

---

## 2. De vier condities voor het model

`run_llm.py` kan het model vier hoeveelheden context geven. Elke conditie bevat de vorige:

| Conditie | Wat het model krijgt |
|---|---|
| `C1_query` | alleen de originele query |
| `C2_schema` | + kolommen, constraints en indexen van de gebruikte tabellen |
| `C3_plan` | + `EXPLAIN (ANALYZE, BUFFERS)` van het origineel |
| `C4_stats` | + geschatte rijen per tabel en `pg_stats` van de gebruikte kolommen |

De context wordt gebouwd in `llm/context.py` (`build_context`). De tabellen en kolommen worden met sqlglot uit de originele query gehaald, dus er is geen handmatige lijst nodig. Kies met `--conditions` welke condities draaien.

---

## 3. Mapstructuur en bestanden

```
.
├── README.md
├── requirements.txt
├── scripts/                      # de uitvoerbare programma's
│   ├── start_db.py               # start de ingebedde PostgreSQL, print de URI
│   ├── stop_db.py                # stopt de database
│   ├── run_validation.py         # mutatietest; bevat ook evaluate(), dat run_llm.py hergebruikt
│   ├── run_llm.py                # LLM laten herschrijven en elk antwoord beoordelen
│   └── analyse.py                # leest results/, maakt tabellen en figuren
├── cases/                        # wat er wordt getest
│   ├── cases.py                  # de 4 Case-objecten, parametersets en alle handgemaakte herschrijvingen
│   ├── classes/
│   │   ├── candidate.py          # dataclass Candidate: naam, sql, verwacht oordeel, fouttype
│   │   └── case.py               # dataclass Case: origineel, ORDER BY-kolommen, parametersets, kandidaten
│   └── original/                 # de 4 originele SUE-query's (.sql)
├── validator/                    # het framework
│   ├── checker.py                # static_check, run_query, compare
│   ├── normalize.py              # norm_value, norm_row
│   ├── timing.py                 # measure; SPEEDUP_THRESHOLD = 1.2
│   └── classes/
│       ├── comparison.py         # dataclass Comparison (status + detail)
│       └── result.py             # dataclass Result (kolommen, rijen, ms)
├── llm/                          # de LLM-koppeling
│   ├── context.py                # bouwt de context per conditie (schema, plan, statistieken)
│   └── client.py                 # systeemprompt, prompt bouwen, API-aanroep, SQL uitpakken
└── results/                      # uitvoer van de runs (zie hieronder)
```

Er zijn bewust geen `__init__.py`-bestanden (Python-namespacepakketten). De scripts voegen de repo-map toe aan het zoekpad en alle imports beginnen bij die map, bijvoorbeeld `from validator.checker import compare`. **Draai de scripts daarom altijd vanuit de hoofdmap van de repository** (`python scripts/...`) en markeer geen submappen als *Sources Root* in een IDE.

### De belangrijkste functies

| Functie | Bestand | Wat het doet |
|---|---|---|
| `static_check(sql)` | `validator/checker.py` | Parsed de SQL en keurt alles af wat geen enkele `SELECT` is |
| `run_query(conn, sql, params, timeout_ms)` | `validator/checker.py` | Voert uit in een read-only transactie en rolt altijd terug |
| `compare(orig, cand, order_cols)` | `validator/checker.py` | Vergelijkt twee resultaten; geeft een `Comparison` |
| `measure(conn, orig_sql, cand_sql, params, reps=7, warmup=2)` | `validator/timing.py` | ABAB-meting; geeft mediaan en speedup |
| `evaluate(conn, case, cand, ctx, reps)` | `scripts/run_validation.py` | Volledige keten voor één kandidaat; geeft het eindoordeel |
| `make_ctx(conn)` | `cases/cases.py` | Zoekt grote en kleine tenant en bouwt de tijdvensters |
| `build_context(conn, case, ctx, condition)` | `llm/context.py` | Bouwt de contextblokken voor een conditie |
| `build_prompt(blocks)` | `llm/client.py` | Zet de blokken om in de prompt |
| `call_llm(prompt, model, max_tokens=4000, original_sql="")` | `llm/client.py` | Roept de API aan (of het nepmodel) |
| `extract_sql(text)` | `llm/client.py` | Haalt de SQL uit het antwoord van het model |

### Volgorde van aanroepen in `run_llm.py`

Per query, conditie en herhaling:

1. `make_ctx(conn)`: grote en kleine tenant en tijdvensters.
2. `build_context(...)`, dan `build_prompt(...)`.
3. `call_llm(...)`, dan `extract_sql(...)`.
4. `evaluate(...)`, dat `static_check`, `run_query`, `compare` en `measure` aanroept.
5. Het resultaat wordt opgeslagen in `results/llm-<tijdstempel>/`.

### Wat in `results/` komt

Alle scripts schrijven hun uitvoer naar `results/`, in een nieuwe map met tijdstempel. **Bestaande mappen worden nooit overschreven.**

| Map of bestand | Gemaakt door | Inhoud |
|---|---|---|
| `validation-<tijdstempel>.csv/.json` | `run_validation.py` | Oordeel per handgemaakte kandidaat |
| `llm-<tijdstempel>/prompts/` | `run_llm.py` | Precies wat het model kreeg, per query en conditie (`_system.txt` bevat de regels) |
| `llm-<tijdstempel>/responses/` | `run_llm.py` | Ruw antwoord, uitgepakte SQL en tokengebruik |
| `llm-<tijdstempel>/llm-results.csv/.json` | `run_llm.py` | Oordeel per antwoord |
| `analyse/` | `analyse.py` | Tabellen (`analyse.txt`, `per_*.csv`), `voorbeelden.md` en figuren |

---

## 4. Wat je nodig hebt

- Python **3.12** (via conda). Andere versies kunnen mislukken: `pgserver` levert op Windows alleen wielen voor Python 3.9 t/m 3.12.
- Git.
- Internet voor `pip install` en het klonen van de SUE-repo.
- Een **Anthropic API-sleutel**, alleen voor de echte LLM-runs (stap 11).
- Enkele GB vrije schijfruimte voor de database en de runs.

Voor de mutatietest, het bekijken van prompts, de A/A-controle en de analyse is na de installatie **geen API-sleutel** nodig. De analyse heeft zelfs geen database nodig.

---

## 5. Installeren en draaien, stap voor stap

De stappen zijn geschreven voor **Windows met PowerShell** (bijvoorbeeld de terminal in PyCharm) en conda. Waar Linux of macOS verschilt, staat het erbij.

### Stap 1. Deze repository klonen

```powershell
git clone https://github.com/Khaled-Alkahlout/initial_poc_sue.git
cd initial_poc_sue
```

Pas de URL aan als de repository een andere naam of eigenaar heeft. Deze map heet hieronder de **repo-map**.

### Stap 2. Conda-omgeving maken

```powershell
conda create -n sqlvalidator python=3.12 -y
conda activate sqlvalidator
python --version      # moet Python 3.12.x tonen
```

### Stap 3. Pakketten installeren

```powershell
pip install -r requirements.txt
pip install matplotlib        # optioneel: alleen nodig voor de figuren van analyse.py
```

`requirements.txt` bevat `pgserver`, `psycopg[binary]`, `sqlglot` en `anthropic`.

### Stap 4. De SUE-repo ophalen en een werkkopie maken

Het schema en de testdata komen uit de repo van SUE. Gebruik een **kopie**, want er wordt één regel aangepast. Zet de SUE-map naast de repo-map:

```powershell
cd ..
git clone https://github.com/robinverstraelen/sql-performance-challenge.git
cd sql-performance-challenge
git checkout 6951dfc          # de versie waarmee deze testbank is gebouwd
cd ..
Copy-Item -Recurse sql-performance-challenge sql-performance-challenge-lab
```

Open in de kopie `sql-performance-challenge-lab\migrations\versions\0001_tenancy.py` en verwijder of becommentarieer de regel:

```python
op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
```

`pgserver` bevat de extensie `pgcrypto` niet. De functie `gen_random_uuid()` zit in PostgreSQL zelf, dus de rest werkt.

Installeer de pakketten die de SUE-code nodig heeft (in dezelfde omgeving):

```powershell
pip install "sqlalchemy>=2.0.30" "alembic>=1.13" "pydantic>=2.7" "pydantic-settings>=2.3" "structlog>=24.1" "faker>=25.0" "rich>=13.7" "typer>=0.12" "fastapi>=0.115"
```

### Stap 5. De database starten

Vanuit de **repo-map**:

```powershell
python scripts/start_db.py C:\pgdata\bazaar
```

Het script maakt de map aan en start een ingebedde PostgreSQL 16.2. Het **print één regel: de URI** van de database. Kopieer die volledig. De poort verandert bij elke start. De server blijft draaien nadat het script klaar is.

Zet de URI in een variabele, zodat je hem niet steeds hoeft te plakken:

```powershell
$URI = "postgresql://...      # plak hier de geprinte URI"
```

Linux of macOS: `URI="postgresql://..."` en gebruik bijvoorbeeld `/tmp/pgdata/bazaar` als datamap.

### Stap 6. Het schema aanmaken (migraties)

Ga naar de **SUE-werkkopie** en zet dezelfde URI met het voorvoegsel `postgresql+psycopg://` in plaats van `postgresql://`:

```powershell
cd ..\sql-performance-challenge-lab
$env:BAZAAR_DATABASE_URL = $URI -replace '^postgresql://', 'postgresql+psycopg://'
python -m alembic upgrade head
```

Verwacht: **25 regels "Running upgrade"** en geen foutmelding.

### Stap 7. De data genereren

Nog steeds in de SUE-werkkopie:

```powershell
python -m seed.generate --scale 0.02 --seed 42 --database-url $URI --manifest manifest.json
```

- `--scale 0.02` betekent 2% van het aantal rijen van de volledige dataset (ongeveer 60.000 orders en 10.000 klanten). De generator verzint alle data.
- `--seed 42` bepaalt de willekeurige keuzes.
- Verwacht: een voortgangsbalk en aan het eind een regel `done in ...s (scale 0.02, seed 42, anchor ...)`.

> **Let op voor exact herhalen.** Dezelfde seed en schaal geven alleen identieke data als ook de **anchor** gelijk is: het "nu" waaraan alle tijdstempels hangen. Standaard is dat het huidige uur. Wie de data in een ander uur genereert, krijgt dezelfde vorm met andere tijdstempels. Geef bij een exacte herhaling `--anchor <ISO-tijdstip>` mee, bijvoorbeeld `--anchor 2026-10-26T12:00:00`.

**Controle** (terug in de repo-map, de database moet nog draaien):

```powershell
cd ..\initial_poc_sue
python -c "import psycopg,sys; c=psycopg.connect(sys.argv[1]); print(c.execute('select count(*) from orders').fetchone())" $URI
```

Verwacht: een aantal rond 60.000.

### Stap 8. De mutatietest draaien

Vanuit de repo-map:

```powershell
python scripts/run_validation.py $URI --reps 5
```

Dit duurt enkele minuten. Onderaan staat de samenvatting, met drie regels waar je op let:

```
Fout (niet-gelijkwaardig) gedetecteerd: 16/17
Foute afkeuringen van gelijkwaardige kandidaten: 0/5
Gemist: ['M3_geen_id_tiebreak']
```

Dit is ook een **installatiecontrole**: komen jouw getallen hiermee overeen, dan werken database, data en validator zoals bedoeld. Een iets ander getal is geen fout van jou, maar controleer dan eerst stap 7 (data en anchor). De uitvoer staat in `results/validation-<tijdstempel>.csv` en `.json`.

### Stap 9. De prompts bekijken zonder LLM (gratis)

```powershell
python scripts/run_llm.py $URI --dry-run
```

Er wordt geen API aangeroepen. Het script bouwt de context uit de database, print per query en conditie de lengte van de prompt en schrijft de prompts naar `results/llm-<tijdstempel>/prompts/`.

### Stap 10. De A/A-controle draaien

```powershell
python scripts/run_llm.py $URI --model mock --reps 3
```

Het nepmodel geeft de originele query terug, de rest van de keten is echt. Dit geeft 4 × 4 × 3 = 48 metingen. Elke `ACCEPTED` hier is meetruis. Verwacht: geen of nauwelijks `ACCEPTED`, en een speedup rond 1,0.

### Stap 11. De API-sleutel instellen

Maak een sleutel aan via console.anthropic.com. Zet hem **alleen in de terminal**, nooit in een bestand dat in git komt:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."          # PowerShell
# cmd:    set ANTHROPIC_API_KEY=sk-ant-...
# Linux:  export ANTHROPIC_API_KEY="sk-ant-..."
```

Dit geldt alleen voor het huidige terminalvenster. Zonder sleutel stopt `run_llm.py` met de melding dat `ANTHROPIC_API_KEY` ontbreekt.

### Stap 12. De echte LLM-run

Eerst een kleine proef om te zien dat alles werkt en wat het kost:

```powershell
python scripts/run_llm.py $URI --model claude-sonnet-5-5 --cases revenue_orders --conditions C1_query C3_plan --reps 1
```

Daarna een volledige run, bijvoorbeeld per query:

```powershell
python scripts/run_llm.py $URI --model claude-sonnet-5-5 --cases revenue_orders --reps 3
python scripts/run_llm.py $URI --model claude-sonnet-5-5 --cases top_products   --reps 3
python scripts/run_llm.py $URI --model claude-sonnet-5-5 --cases audit_log_page --reps 3
python scripts/run_llm.py $URI --model claude-sonnet-5-5 --cases top_customers  --reps 3
```

Alles in één keer kan ook: laat `--cases` weg. Een LLM is niet deterministisch, dus een tweede run met dezelfde instellingen geeft niet exact dezelfde antwoorden.

**Opties van `run_llm.py`:**

| Optie | Standaard | Betekenis |
|---|---|---|
| `uri` | verplicht | de database-URI |
| `--model` | `claude-sonnet-5-5` | Anthropic-modelnaam, of `mock` |
| `--reps` | 3 | LLM-aanroepen per query per conditie |
| `--val-reps` | 7 | tijdmetingen per gelijkwaardige herschrijving |
| `--cases` | alle vier | lijst van query's |
| `--conditions` | alle vier | lijst van condities |
| `--dry-run` | uit | alleen prompts opslaan |

De kosten zijn te schatten uit de proefrun: het tokengebruik staat per antwoord in `responses/`.

### Stap 13. De analyse draaien

```powershell
python scripts/analyse.py
```

Dit heeft **geen database en geen API-sleutel** nodig, het leest alleen `results/`. Het kiest automatisch de volledige runs (echt model, alle vier de condities) en gebruikt de mock-mappen voor de ruisband. Met `--map <mappen>` kies je zelf mappen. De uitvoer staat in `results/analyse/`:

- `analyse.txt`: het volledige verslag met tabellen
- `per_poging.csv`, `per_conditie.csv`, `per_casus_conditie.csv`: de data in tabelvorm
- `voorbeelden.md`: goede en foute voorbeelden met SQL
- `uitkomsten.png`, `speedup.png`: figuren (alleen met matplotlib)

### Stap 14. De database stoppen

```powershell
python scripts/stop_db.py C:\pgdata\bazaar
```

Gebruik dezelfde datamap als bij de start. Stop de database altijd voordat je de computer uitzet; zie hoofdstuk 7 voor wat er anders kan gebeuren.

### Snelle herstart op een volgende dag

```powershell
conda activate sqlvalidator
cd initial_poc_sue
python scripts/start_db.py C:\pgdata\bazaar     # nieuwe URI, de poort is veranderd
```

De data blijft bewaard in `C:\pgdata\bazaar`. Je hoeft stap 6 en 7 niet te herhalen.

---

## 6. Een eigen query toevoegen

Alle scripts lezen de lijst `CASES` onderaan `cases/cases.py`. Een nieuwe query toevoegen gaat in vier stappen:

1. **Zet de query in `cases/original/<naam>.sql`.** Gebruik `%(naam)s`-plaatsvervangers voor parameters (zoals `%(tenant_id)s`, `%(from)s`, `%(to)s`, `%(limit)s` in de bestaande query's).
2. **Lever parametersets.** Hergebruik `std_params(limit)` als je query dezelfde parameters heeft als de bestaande, of schrijf een functie `f(ctx)` die een lijst `(label, dict)` teruggeeft. Voor de tijdmeting is `std_timing(limit)` of een eigen functie `f(ctx)` die één dict teruggeeft.
3. **Maak (optioneel) handgemaakte kandidaten** voor de mutatietest:

   ```python
   Candidate(name="M1_filter_weg", sql="...", expected="not_equivalent", fault="filter_weggelaten")
   Candidate(name="E1_cte_herschrijving", sql="...", expected="equivalent", fault="-")
   ```

4. **Voeg een `Case` toe aan `CASES`:**

   ```python
   Case("mijn_query", original("mijn_query"), ["kolom_a", "kolom_b"], std_params(1000), std_timing(1000), MIJN_CANDS)
   ```

   Het derde argument is de lijst met kolommen die de `ORDER BY` bepalen, of `None` als het origineel geen `ORDER BY` heeft.

Daarna werkt `--cases mijn_query` in `run_llm.py`, doet `run_validation.py` de kandidaten mee en neemt `analyse.py` de query op.

Een query die niet op de SUE-database draait, vraagt een eigen database en een eigen `make_ctx` (die nu `orders` en `tenant_id` aanneemt).

---

## 7. Problemen oplossen

| Melding of gedrag | Oorzaak en oplossing |
|---|---|
| `ModuleNotFoundError: No module named 'classes'` of `'cases'` | Je draait niet vanuit de repo-map, of de IDE heeft `cases/` of `validator/` als *Sources Root* gemarkeerd. Draai `python scripts/...` vanuit de repo-map en markeer geen submappen als Sources Root. |
| PyCharm toont "Import resolves to its containing file" bij `cases.py` | Alleen een waarschuwing van de statische analyse: het bestand `cases.py` heeft dezelfde naam als de map `cases`. Het script draait gewoon. Negeren. |
| `TypeError: Could not resolve authentication method` of "Zet eerst de omgevingsvariabele ANTHROPIC_API_KEY" | De sleutel is niet gezet in **dit** terminalvenster. Zie stap 11. |
| `start_db.py` blijft hangen of geeft een timeout van ongeveer 10 seconden na een herstart of uitzetten zonder stoppen | De database moet herstellen na een onjuiste afsluiting en Windows houdt het logbestand nog vast ("sharing violation"). Wacht een minuut en start opnieuw. Controleer daarna het aantal orders (stap 7) en draai `run_validation.py`. Stop de database voortaan met `stop_db.py`. |
| De URI werkt niet meer | De poort verandert bij elke start. Gebruik de URI die `start_db.py` nu print. |
| `alembic` mislukt op `pgcrypto` | De regel in `0001_tenancy.py` is nog niet verwijderd (stap 4). |
| `analyse.py`: "geen figuren: matplotlib niet geinstalleerd" | `pip install matplotlib`. De tabellen worden wel gemaakt. |
| `analyse.py`: "Geen volledige runs gevonden" | `results/` bevat geen map met `llm-results.csv` van een echt model met alle vier de condities. Draai stap 12 of geef `--map` mee. |

---

## 8. Technische beperkingen

- **Geen bewijs van gelijkwaardigheid.** `ACCEPTED` betekent: gelijk resultaat op de geteste parametersets en minstens 1,2× sneller. De validator bewijst niet dat een herschrijving voor alle mogelijke data gelijk is. Een fout die de testdata niet zichtbaar maakt, wordt gemist (voorbeeld: `M3_geen_id_tiebreak`, omdat in `audit_log` de combinatie tenant en tijd uniek is).
- **Verzonnen, kleine data.** Standaard schaal 0,02 met 3 tenants. Op een grotere of echte database kunnen queryplannen en tijden anders zijn. Op schaal 0,05 duurde `top_customers` al 34 tot 56 seconden per uitvoering.
- **Tijdmetingen op één machine.** Gedaan met de standaardinstellingen van een ingebedde PostgreSQL 16.2 en niet vergelijkbaar met de bewust slechte `postgresql.conf` van SUE. `pg_stat_statements` en `auto_explain` zitten niet in `pgserver` en worden niet gebruikt.
- **De drempel 1,2× is een ontwerpkeuze.** Meet de ruis van je eigen machine met de A/A-controle (stap 10) voordat je de drempel vertrouwt. Met 3 herhalingen per meting gaf de A/A-controle wel onterechte `ACCEPTED`-oordelen; daarom zijn 7 herhalingen de standaard. Een uitkomst van 0 onterechte `ACCEPTED` bij 48 metingen betekent niet dat de kans nul is: het exacte 95%-interval loopt dan tot ongeveer 7%.
- **Eigen labels.** Het verwachte oordeel (`expected`) van de handgemaakte kandidaten is de redenering van de maker en niet onafhankelijk bewezen.
- **Categorie "ongewijzigd" in de analyse.** `analyse.py` berekent dit opnieuw uit genormaliseerde SQL (commentaar, witruimte en afsluitende `;` genegeerd), omdat de vlag `unchanged` in de ruwe resultaten onjuist is wanneer het model de commentaarkop weglaat.
- **LLM-uitkomsten wisselen.** Een model geeft bij een herhaalde run niet dezelfde antwoorden.
- **Platform.** Getest op Windows met conda en Python 3.12; eerder ook op Linux.

---

## 9. Bronnen

- Webshop, schema en datagenerator: SUE, repository `robinverstraelen/sql-performance-challenge`, commit `6951dfc`. Dit is code van SUE en geen onderdeel van deze repository.
- Ingebedde PostgreSQL: [`pgserver`](https://pypi.org/project/pgserver/). SQL-parser: [`sqlglot`](https://pypi.org/project/sqlglot/). Database-driver: `psycopg` 3.
- Model: `claude-sonnet-5-5` via de Anthropic API.

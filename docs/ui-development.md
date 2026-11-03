# Dashboard lokaal ontwikkelen en demonstreren

## Vereisten

- Node.js 22.12 of hoger; getest met 22.19.0.
- Python 3.12 of 3.13 voor de offline API; getest met 3.13.7.
- npm en een gewone lokale browser.

Demo/replay vereist geen PostgreSQL, Anthropic-key, AWS of betaalde service.
`requirements-api.txt` bevat alleen de API en bestaande SQL-parser.
`requirements-dev.txt` voegt de HTTP-testclient toe. De bestaande
`requirements.txt` en CLI-workflows blijven beschikbaar.

## Installeren

Vanuit de repositoryhoofdmap, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd frontend
npm ci
cd ..
```

Linux/macOS: vervang `.venv\Scripts\python.exe` door `.venv/bin/python`.
Het frontend-lockbestand legt npm-resoluties vast. Er worden geen remote fonts
of afbeeldingen tijdens de productiebuild opgehaald.

## Starten: twee terminals

Terminal 1, in de repositoryhoofdmap:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd frontend
npm run dev
```

Open <http://127.0.0.1:3000>. De frontend proxy't `/api` lokaal naar FastAPI.
De API-documentatie staat op <http://127.0.0.1:8000/docs>.
Stop services in hun terminal met Ctrl+C. Start één API-worker; gebruik niet
meerdere Uvicorn-workers voor deze lokale SQLite/queue-opstelling.

Voor de productiebuild, zonder publieke deployment:

```powershell
cd frontend
npm run build
npm start
```

## Demonstratiescenario zonder credentials

1. Open **Overzicht**: vier fixtures, mockimpact en historische experimenten.
2. Open **Query Explorer**: sorteer, zoek, wijzig het weergavebudget en bekijk
   de redencodes bij een query. Workloadcijfers zijn expliciet fictief.
3. Open `top_products`: SQL, metrics, selectie en opgeslagen context.
4. Klik **Demo starten**, kies **Historische replay** en een contextconditie.
5. De nieuwe run gaat van wachtrij naar voltooid. Inspecteer SQL naast elkaar,
   fases en historische benchmark. Er wordt niets opnieuw gemeten.
6. Sla een ontwikkelaarsreview op. Herladen toont de review nog steeds; de
   technische conclusie blijft hetzelfde.
7. Open **Development → Tests & evaluatie**. Inspecteer bijvoorbeeld de gemiste
   `audit_log_page / M3_geen_id_tiebreak`-mutant, of vergelijk contextcondities.
8. Open **Tests uitvoeren → Filtering & ranking**. De bestaande unittest-suite
   draait echt; nieuwe resultaten zijn individueel inspecteerbaar.
9. Open **Architectuur & diagnostiek**: configuratie, prerequisites en grenzen.

Een **Offline mock**-run demonstreert nieuw uitgevoerde selectie, mockgeneratie
en statische controle. Hij markeert correctheid en benchmark terecht als niet
uitgevoerd. C1 is de enige beschikbare contextconditie voor deze modus.

## Configuratie

| Instelling                      | Betekenis                                                       |
| ------------------------------- | --------------------------------------------------------------- |
| `API_ORIGIN`                    | Server-side Next.js-instelling, default `http://127.0.0.1:8000` |
| `SUE_DATA_DIR`                  | Pythonopslag, default `<repo>/.local`                           |
| `SUE_ENABLE_SQL_RUNS=1`         | Live SQL-operaties expliciet aanbieden                          |
| `SUE_TEST_DATABASE_CONFIRMED=1` | Operator bevestigt een geïsoleerd testdoel                      |
| `SUE_DATABASE_URL`              | Alleen server-side DSN van de testdatabase                      |
| `SUE_ENABLE_LLM=1`              | Externe modelgeneratie expliciet aanbieden                      |
| `SUE_MODEL`                     | Expliciet gekozen provider-model-ID                             |
| `ANTHROPIC_API_KEY`             | Alleen server-side modelcredential                              |

De Python-API leest procesvariabelen; `.env.example` wordt niet automatisch
geladen. Gebruik bijvoorbeeld `$env:SUE_ENABLE_SQL_RUNS="1"` vóór Uvicorn.
Next.js kan `frontend/.env.local` gebruiken voor `API_ORIGIN`.
Gebruik geen `NEXT_PUBLIC_*`-variabelen voor credentials. De voorbeeldbestanden
bevatten geen werkende credentials; echte `.env`-bestanden worden genegeerd.

## Optionele testdatabase- en live-operaties

Deze routes zijn geïmplementeerd, maar zijn niet tijdens de dashboardvalidatie
tegen een echte database/provider uitgevoerd.

1. Bereid de bestaande Bazaar-testdatabase voor volgens de oorspronkelijke
   README. Voor ingebedde pgserver op Windows blijft Python 3.12 de beschreven
   compatibele keuze. Een reeds draaiende testdatabase vereist geen pgserver.
2. Installeer `psycopg[binary]`; voor live generatie ook `anthropic`.
3. Configureer uitsluitend een geïsoleerde testdatabase, met een beperkte rol.
4. Zet SQL-enablement, testdoelbevestiging en de server-side DSN vóór API-start.
5. **Testdatabase · mockmodel** gebruikt bestaande context en evaluate, zonder
   externe modelcall. SQL-uitvoering moet ook in de browser worden bevestigd.
6. Voor **Live POC** zijn daarnaast model-enablement, model-ID en key nodig.
   Bevestig het externe request afzonderlijk. De run genereert precies één
   voorstel voor één vooraf gedefinieerde case; geen feedbacklus.

Alle contextcondities blijven beschikbaar waar hun prerequisites aanwezig zijn.
C3/C4 voeren `EXPLAIN ANALYZE` uit. De oude CLI-`--dry-run` is dus nog steeds
geen offline selectie. De nieuwe dashboardreplay en offline mock zijn dat wel.

## Tests en checks

Vanuit de repositoryhoofdmap:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Dit omvat bestaande domeintests, API-contracten, artifactparsing, reviewopslag,
queue/timeout, statusadaptatie en echte lokale replay/mock/testworkers. Alleen
nieuwe testdatabases in tijdelijke mappen worden geschreven, geen PostgreSQL.

Frontend:

```powershell
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
```

Voor browser-smoketests moeten beide servers al draaien:

```powershell
# Gebruik een geïnstalleerde Edge zonder browserdownload:
$env:PLAYWRIGHT_CHANNEL="msedge"
npm run test:e2e
```

Zonder channel gebruikt Playwright zijn eigen Chromium; installeer dat zo nodig
met `npx playwright install chromium`. `UI_BASE_URL` kan de lokale test-URL
overschrijven. E2E-tests schrijven uitsluitend replaytaken en duidelijk
herkenbare testreviews in de lokale dashboardopslag. Historische bestanden
blijven ongewijzigd.

In een beperkte Windows-sandbox kunnen asyncio/socketpair, browserprocessen en
tempfile-renames geblokkeerd zijn. Voer de lokale tests dan in een normale
ontwikkelterminal uit. Tijdens deze implementatie was die beperking aanwezig;
API- en browsertests zijn daarom buiten die sandbox uitgevoerd. Voor tijdelijke
testbestanden werd een map binnen de lokale `.venv` gebruikt.

## Problemen oplossen

| Symptoom                        | Controle                                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------------------------- |
| API niet bereikbaar             | Draait Uvicorn op 127.0.0.1:8000? Klopt server-side `API_ORIGIN`?                                 |
| Contractfout                    | Vergelijk Pydantic- en Zod-contracten; de UI toont geen fake fallback.                            |
| Live modus niet beschikbaar     | Bekijk diagnostiek; configuratie, attestation en SDK zijn afzonderlijke vereisten.                |
| Nieuwe CLI-resultaten ontbreken | Herstart de API: historische bestanden worden bij startup geïmporteerd.                           |
| Run onderbroken                 | Worker-timeout of API-herstart; inspecteer de geregistreerde fout. Geen automatische hervatting.  |
| Wachtrij vol                    | Eén actieve en één wachtende taak zijn toegestaan.                                                |
| Feedback ontbreekt na herstart  | Gebruik hetzelfde `SUE_DATA_DIR`; opslag is een lokale SQLite-database.                           |
| Geen schema/plan                | Conditie bevat die informatie niet, of het bronartefact ontbreekt. Inspectie haalt niets live op. |
| SQL bevat geredigeerde waarden  | Dit is de veilige browserweergave; het oorspronkelijke artefact is niet aangepast.                |

Geen publieke hosting, authenticatie of production deployment is onderdeel van
deze taak. Bind de uitvoering-API niet zonder aanvullende beveiliging publiek.

# OpenRouter-analyse en afzonderlijke validatie

Voor configureerbare tokenlimieten, reasoning, persistente voorkeuren en volledige
responsdiagnostiek: [AI Settings](ai-settings.md). Het SQL-analysepad gebruikt nu
standaard 4096 tokens en low effort. De nieuwe Settings-verbindingstest doet één
klein betaald generatieverzoek; de oorspronkelijke key/catalogustest blijft kosteloos.

Deze wijziging bouwt voort op Next.js/React/TypeScript, FastAPI/Pydantic,
`query_selection/`, de vier bestaande cases, de artifactadapter en SQLite.
De oorspronkelijke validator en experimentele CLI-workflows blijven behouden.

## Wat is veranderd?

- `llm/analysis.py`: OpenRouter HTTP-client, exact model controleren, beperkt
  JSON-schema, Pydantic-validatie, timeouts, veilige fouten en usage/kostenmetadata.
- `api/services/analysis.py`: selectie → geredigeerde historische context → één
  modelcall → statische controle → ongetest advies opslaan. Geen database vereist.
- Afzonderlijke `validate`-run: leest uitsluitend het opgeslagen voorstel,
  controleert veiligheidsinstellingen en voert bestaande `evaluate()` uit.
- Querydetail is nu de Analysis Workspace, met expliciet **Analyze with AI**,
  voortgang, verklaring, risico's, SQL-vergelijking en aparte validatieactie.
- Analysehistorie gebruikt dezelfde runopslag. Reviews blijven afzonderlijk.
- Systeemstatus toont provider/model en SQL-instellingen; de OpenRouter-test
  controleert key en catalogus zonder betaalde generatie of databasequery.
- Explorer heeft metricfilters en paginering van 25 rijen. Filtering en ranking
  blijven Python-logica; presentatiefilters wijzigen geen analysebeleid.

```mermaid
flowchart TD
    Query["Query Explorer → Analysis Workspace"] --> API["POST /api/runs · analysis"]
    API --> Queue["Begrensde worker + deduplicatie"]
    Queue --> Select["Bestaande filtering + prioritering"]
    Select --> Context["Fixture-SQL + geredigeerde historische context"]
    Context --> Model["OpenRouter: exact geconfigureerd model"]
    Model --> Contract["JSON-schema + Pydantic + SQL-admission"]
    Contract --> Store[("SQLite: ongetest advies + metadata")]
    Store --> UI["Uitleg, SQL-vergelijking, risico's"]
    UI -->|"apart bevestigd"| Validate["POST /api/runs · validate"]
    Validate --> Gates["Beide SQL-flags + bevestiging + static checks"]
    Gates --> DB[("Geïsoleerde testdatabase · read-only")]
    DB --> Result["Correctheid en benchmark afzonderlijk"]
```

## Configuratie en installatie

Installeer vanuit de repositoryhoofdmap:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd frontend
npm ci
cd ..
```

Maak lokaal `.env` op basis van `.env.example` en vul de key zelf in:

```dotenv
SUE_ENABLE_SQL_RUNS=0
SUE_TEST_DATABASE_CONFIRMED=0
SUE_ENABLE_LLM=1
SUE_LLM_PROVIDER=openrouter
SUE_MODEL=anthropic/claude-haiku-5.5
OPENROUTER_API_KEY=
```

FastAPI laadt `.env` uit de repositoryhoofdmap met `override=False`:
procesvariabelen hebben voorrang. Herstart de API na configuratiewijzigingen.
De worker erft dezelfde configuratie. Keys gaan uitsluitend server-side mee in
de Authorization-header, nooit naar frontendcontracten of commandline-argumenten.
`.env` blijft door Git genegeerd; alleen `.env.example` is versieerbaar.

Voor directe Anthropic-backward compatibility kies je expliciet
`SUE_LLM_PROVIDER=anthropic`, een rechtstreeks Anthropic-model-ID en
`ANTHROPIC_API_KEY`. De keys worden niet uitgewisseld of als fallback gebruikt.
Zonder expliciete provider wordt een model-ID met `/` als OpenRouter behandeld;
een legacy-model-ID zonder `/` als directe Anthropic-configuratie.

Het opgegeven ID `anthropic/claude-haiku-5.5` is op 3 november 2026 aangetroffen
in de [officiële modelcatalogus](https://openrouter.ai/api/v1/models), met
Chat Completions en structured-outputondersteuning. De software controleert de
catalogus opnieuw vóór generatie (maximaal 60 seconden cache). Een ontbrekend
model leidt tot een duidelijke fout, zonder alternatief model of herstelcall.
Catalogusbeschikbaarheid bewijst geen geslaagde generatie met jouw account.

De client gebruikt `https://openrouter.ai/api/v1/chat/completions` met
Bearer-authenticatie en `response_format: json_schema`, volgens de
[structured-outputdocumentatie](https://openrouter.ai/docs/guides/features/structured-outputs).
Er is geen extra OpenAI SDK nodig; `httpx` verzorgt de compatibele HTTP-aanroep.

## Lokaal starten en demonstreren zonder database

**POC starten** kiest standaard **Live POC · echt AI-advies (zonder database)**
wanneer model, providerkey en LLM-enablement aanwezig zijn. De aparte modus
**AI + databasevalidatie · experimenteel** vereist ook de testdatabase. Een
ontbrekende testdatabase blokkeert dus geen echt AI-advies. Replay blijft
handmatig selecteerbaar en start geen extern modelrequest.

Een OpenRouter-key hoort onder `OPENROUTER_API_KEY`, ook voor een Anthropic-model.
Een key onder de verkeerde providernaam geeft een gerichte configuratiefout;
keys worden niet stilzwijgend naar een andere provider gestuurd.

Terminal 1, repositoryhoofdmap:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd frontend
npm run dev
```

1. Open <http://127.0.0.1:3000/queries> en kies bijvoorbeeld `top_products`.
2. Inspecteer SQL en fictieve workloadimpact. 100.000 uitvoeringen × 5 ms
   levert 500.000 ms mockimpact; dat is geen gemeten databasebelasting.
3. Controleer OpenRouter via **Systeemstatus**. De keytest gebruikt alleen
   `GET /key` en de openbare modelcatalogus, geen generatie.
4. Bevestig in de workspace het externe request en klik **Analyze with AI**.
5. De worker doet één request en bewaart gevalideerde gestructureerde output.
   Fouten, ontbrekend model en ongeldige output worden zichtbaar gerapporteerd.
6. Inspecteer hypothese, rewrite, indexadvies, ontbrekende context en risico's.
   Validatie en benchmark staan terecht op niet uitgevoerd/niet beschikbaar.
7. Open de analyse opnieuw via **Analysehistorie** of de querydetailpagina.

Een echte AI-demonstratie heeft een geldige OpenRouter-key en tegoed nodig.
Zonder credentials blijven historische replay en offline mock beschikbaar.
Mock/replay worden nooit als nieuwe AI-generatie gepresenteerd.

## Output, begrenzing en kosten

Het model levert negen velden: `problem`, `root_cause`, `optimized_sql`
(nullable), `index_recommendations`, `expected_benefit`, `correctness_risks`,
`uncertainty`, `validation_recommendations` en `missing_context`.
Extra velden, verkeerde typen, te grote of afgekapt ontvangen antwoorden worden
afgewezen. Er volgt geen automatische LLM-feedback- of herstelcall.

Eén case wordt vóór contextopbouw geselecteerd met de bestaande module. De bron
is voorlopig de mockadapter; er is geen nieuwe telemetrycollector of SQL-upload.
Historische context is expliciet als mogelijk verouderd gemarkeerd, per blok tot
8000 tekens beperkt en geredigeerd. De exacte tekstblokken staan bij de analyse.
Ontbrekende context wordt niet live opgehaald. SQL-literals/parameters worden
niet stilzwijgend veranderd; een voorstel met gevoelige waarden wordt afgewezen.

Model, provider, duur, tokens en kosten worden opgeslagen waar beschikbaar.
Providerkosten hebben het label gerapporteerd. Anders kan een schatting op basis
van catalogus-tokenprijzen worden getoond, uitsluitend onder bekende prijstiers;
die schatting houdt geen rekening met cachekortingen of aanvullende kosten.
Ontbrekende kosten blijven onbekend, niet nul.

Connect-timeout is 10 seconden, request-timeout 60 seconden. Alleen GET-verzoeken
herhalen hooguit één keer bij tijdelijke netwerkproblemen, 429, 502 of 503.
Generatie wordt nooit automatisch herhaald: een timeout kan al kosten hebben
veroorzaakt. Ook een schema-afwijzing kan een betaald request zijn geweest.
De lokale worker blijft maximaal 300 seconden actief; één taak is actief en één
kan wachten. De opslag voorkomt gelijktijdige dubbele analyse/validatie van
dezelfde query, ook bij dubbele HTTP-aanvragen.

## Een geïsoleerde testdatabase aansluiten

Bereid de bestaande Bazaar-fixtures voor volgens de oorspronkelijke README.
Gebruik een aparte, uitsluitend voor tests bestemde database, met beperkte rol.
Installeer `psycopg[binary]` en configureer server-side:

```dotenv
SUE_ENABLE_SQL_RUNS=1
SUE_TEST_DATABASE_CONFIRMED=1
SUE_DATABASE_URL=postgresql://restricted_test_role:...@localhost:5432/dedicated_test_db
```

Herstart de API. Open een opgeslagen AI-analyse en bevestig de afzonderlijke
validatieactie. Alleen de opgeslagen SQL wordt getest; indexadviezen worden
nooit uitgevoerd. Multi-statements, DDL, INTO, locks en onbekende functies worden
afgewezen vóór verbinding voor deze route. De verbinding is standaard read-only,
met connect-timeout 5 s en statement-timeout 120 s. De bestaande validator gebruikt
bovendien read-only transacties met rollback. Benchmarking gebruikt zeven
herhalingen wanneer de bestaande evaluator die fase toestaat.

Beide flags én browserbevestiging worden server-side gecontroleerd. Een flag is
een operatorverklaring: software kan daarmee niet bewijzen dat een URI werkelijk
geen productieomgeving is. Configureer deze POC daarom uitsluitend voor een
geïsoleerd testdoel en bind hem lokaal, zonder publieke toegang.

## Testbewijs en resterende beperkingen

Gecontroleerd op 3 november 2026:

| Controle                                | Resultaat                                                                                  |
| --------------------------------------- | ------------------------------------------------------------------------------------------ |
| Volledige Python-regressiesuite         | 79 tests geslaagd                                                                          |
| Extra gerichte live-API-safetyregressie | Geslaagd; onveilige model-SQL bereikt evaluate niet                                        |
| Frontendunittests                       | 22 tests geslaagd                                                                          |
| TypeScript en ESLint                    | Geslaagd                                                                                   |
| Ruff check en formatting                | Geslaagd                                                                                   |
| Next.js-productiebuild                  | Geslaagd, inclusief afzonderlijke previewbuild                                             |
| Browser-smoketests                      | 5 geslaagd: replay/review, Development-tests, mobiel, API-fout en AI-workspaceconfiguratie |

De reguliere poorten waren bezet. Browsercontrole gebruikte daarom een aparte
API op 8001, frontend op 3001, eigen `.local/browser-check-nov03`-opslag en
`SUE_PREVIEW=1` voor `.next-preview/`. Dit verandert de standaardpoorten niet.
De bestaande processen zijn niet gestopt. De afzonderlijke previews worden na
controle afgesloten. De AI-knop is in de browser bewust zonder externe requests
getest; provideruitkomsten en validatie zijn via substitutes getest.

Provider-HTTP, schema's, foutmeldingen, geen modelsubstitutie, geen generatie-retry,
deduplicatie, SQL-gates en validatiestatussen hebben onafhankelijke tests zonder
API-key, PostgreSQL of AWS. De browserchecks gebruiken de offline demo. Er is bij
deze wijziging geen echte modelgeneratie of databasebenchmark uitgevoerd.

De validator blijft de bestaande implementatie. Bekende beperkingen rond ties,
normalisatie en foutclassificatie worden conservatief zichtbaar gemaakt via de
adapter; deze wijziging levert geen formeel equivalentiebewijs. Een onbekende
functie wordt voor de nieuwe testactie conservatief geweigerd, ook als die in
een specifieke database veilig zou kunnen zijn.

Echte workloadmonitoring/import, algemene query-equivalentie, automatische
indexcreatie, publieke authenticatie en een production optimizer blijven buiten
scope. De gebruiker ontvangt advies, geen automatisch toegepaste optimalisatie.

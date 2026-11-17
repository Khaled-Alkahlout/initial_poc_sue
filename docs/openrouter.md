# OpenRouter-analyse en validatie op een testdatabase

Voor configureerbare tokenlimieten, reasoning, persistente voorkeuren en volledige
responsdiagnostiek: [AI Settings](ai-settings.md). Het SQL-analysepad gebruikt nu
standaard 4096 tokens en low effort. De nieuwe Settings-verbindingstest doet één
klein betaald generatieverzoek; de oorspronkelijke key/catalogustest blijft kosteloos.

## Keuzes bij de overdracht

| Onderdeel | Geïntegreerd gedrag |
| --- | --- |
| Softwarechecks | De bestaande selectie en casussen blijven de ingang. De gedeelde PostgreSQL-parser controleert het origineel en de kandidaat, inclusief bindingsnamen, tabellen, functies en sorteersleutels. |
| Databaseconnectie | Een taakgebonden psycopg-verbinding gebruikt de bestaande serverconfiguratie, time-outs en een read-only snapshot met rollback. |
| Model en reasoning | De server bepaalt het aanbod. **AI Settings** bewaart het gekozen model en de opties. De worker ontvangt een snapshot van die voorkeuren en controleert modelmogelijkheden vóór generatie. |
| LLM-koppeling | De bestaande OpenRouter-client vraagt één strikt JSON-antwoord op en bewaart beschikbare gebruiksmetadata. Het pakket gebruikt lossere tekstextractie en betaalde retries. De directe Anthropic-client hoort bij de CLI-experimenten. |
| Queryanalyse | C1–C4 hergebruiken de contextopbouw. Live C3 deelt een geschat plan en C4 alleen samengevatte statistieken. Dezelfde modelcall geeft diagnose, rewrite en onderbouwing. |
| Validatie | Volledige runs en opgeslagen voorstellen volgen dezelfde evaluator. Gecontroleerde SQL, toegestane casustabellen en een geldig parameterprofiel zijn vereist. |
| Vergelijking | Kolomtypen, rijmultiset, volgorde en timingparameters worden in dezelfde snapshot gecontroleerd. Meetparen wisselen af welk statement als eerste start. |
| Besluit | `ACCEPTED` vereist volledige correctheid en voldoende snelheidsbewijs. Afwijkingen, onvoldoende bewijs en uitvoeringsfouten hebben aparte statussen. |

De bestaande FastAPI-worker bewaart voortgang, voorstellen en testbewijs in
SQLite. Query Explorer, Analysis Workspace en Run Details lezen dezelfde
contracten. Een medewerker kan een voorstel beoordelen via de bestaande review.

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

`SUE_MODEL` is de standaard. Vul optioneel `SUE_ALLOWED_MODELS` met een
kommagescheiden lijst van extra volledige OpenRouter-ID's. Na een API-herstart
verschijnen de opties in **AI Settings**. Het gekozen model moet gestructureerde
uitvoer en de gekozen generatieopties ondersteunen.

FastAPI laadt `.env` uit de repositoryhoofdmap met `override=False`:
procesvariabelen hebben voorrang. Herstart de API na configuratiewijzigingen.
De worker erft dezelfde configuratie. Keys gaan uitsluitend server-side mee in
de Authorization-header, nooit naar frontendcontracten of commandline-argumenten.
`.env` blijft door Git genegeerd; alleen `.env.example` is versieerbaar.

De dashboardflow gebruikt `SUE_LLM_PROVIDER=openrouter`. Voor directe Anthropic
gebruikt de bestaande CLI een direct model-ID en `ANTHROPIC_API_KEY`.

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

Gebruik **POC starten** of **Analyze with AI** bij de query. Bevestig de mogelijke
AI-kosten om de analyse te starten. Met een ingestelde testdatabase vraagt
**POC starten** ook toestemming voor Correctheid en Benchmark. Zonder
testdatabase voert het scherm alleen de AI-analyse uit. Historische resultaten
staan onder **Analysehistorie**.

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

Het model levert het bestaande analyseschema v2, inclusief
`rewrite_status`, `rewrite_explanation` en één kandidaat in `optimized_sql`.
Een gemotiveerde uitkomst zonder voorstel krijgt een eigen status. Ongeldige
of afgeknotte uitvoer geeft een fout met beschikbare diagnostiek.

De server selecteert één geregistreerde casus. Voor een extra query voeg je op de
server een SQL-bestand, sorteercontract en parameterprofiel toe aan `cases/`.
AI-analyse zonder testdatabase gebruikt C1, met casus-SQL en als zodanig
gelabelde fictieve workload. Live context deelt voor C2 kolom- en indexmetadata,
voor C3 geschatte plannodes uit `EXPLAIN (FORMAT JSON)` en voor C4 alleen
aggregaten uit de statistieken. Plandelen met predicates, resultaatsrijen,
parameterwaarden en lijsten met veelvoorkomende waarden blijven server-side.

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

Gebruik een geïsoleerde testdatabase met de bestaande casustabellen in `public`.
Het overdrachtspakket bevat een kleine synthetische fixture voor een lege,
wegwerpbare database in `transfer_package/tests/fixtures/synthetic.sql`.
Gebruik voor de toepassing een rol met SELECT op de casustabellen en zonder
CREATE- of TEMP-rechten. Installeer `psycopg[binary]` en configureer server-side:

```powershell
.\.venv\Scripts\python.exe -m pip install "psycopg[binary]"
```

```dotenv
SUE_ENABLE_SQL_RUNS=1
SUE_TEST_DATABASE_CONFIRMED=1
SUE_DATABASE_URL=
```

Vul `SUE_DATABASE_URL` in met de DSN voor de geïsoleerde testdatabase, inclusief
de TLS-instellingen die deze database vereist. Voor AWS RDS kun je ook
`ENDPOINT`, `PORT`, `DB_NAME`, `DB_USER` en `DB_PASS` in de server-side `.env`
zetten. Laat `SUE_DATABASE_URL` leeg om deze velden te gebruiken. Hiermee
controleert PostgreSQL het servercertificaat en de hostnaam met `verify-full`.
Download de CA-bundel voor jouw regio en geef het pad naar het PEM-bestand op
in `PGSSLROOTCERT`. [AWS RDS CA-bundels](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)

Herstart de API na het wijzigen van `.env`. Procesvariabelen gaan voor op dit
bestand. Gebruik een host en poort die vanuit Python bereikbaar zijn. Binnen
een container wijst `localhost` naar die container.

Kies **Systeemstatus → Databaseverbinding testen** om de verbinding en de
leesrechten op de casustabellen afzonderlijk te controleren. De test gebruikt
`SELECT 1`, schemametadata en `LIMIT 0` en is ook beschikbaar als de
runvalidatie uitstaat. Schakel beide SQL-vlaggen in voor een geïsoleerd testdoel.

Bevestig de modelaanroep en testuitvoering in **Live POC** of via **Analyseer en
valideer** bij de query. De worker doet eerst `SELECT 1` en controleert toegang
tot de casustabellen in `public`, inclusief `orders` voor het parameterprofiel.
Een verbindings- of schemafout stopt de run voordat het model wordt aangeroepen.
De serverlog vermeldt het run-ID, de fase en foutcategorie, met SQLSTATE wanneer
PostgreSQL dat levert.

Onder **Optimization Results** staan de geteste parametersets en de mediane
tijden. Voor een eerder opgeslagen voorstel kun je **Correctheid & performance
testen** gebruiken. De benchmark wordt overgeslagen bij een resultaatverschil of
ontoereikend correctheidsbewijs. De oorzaak staat bij de fase.

Dashboardruns leiden tijdvensters af uit maximaal 512 recente orders. Zo hoeft
de voorbereiding geen volledige orderhistorie te groeperen. De metingen gelden
voor de daaruit afgeleide parameters op deze database.

De verbinding heeft een connect-timeout van 5 s. Vergelijking gebruikt één
`REPEATABLE READ READ ONLY`-snapshot met een statement-timeout van 2 s en een
slotwachttijd van 500 ms. Een servercursor haalt maximaal 2.001 rijen op. Bij
meer dan 2.000 rijen stopt de vergelijking zonder oordeel. Voor de benchmark
moeten alle sets slagen, inclusief de timingparameters. Die set moet rijen
opleveren en beide queries moeten binnen 500 ms blijven. De benchmark gebruikt
zes paren met afwisselende startvolgorde en 500 ms statement-timeout.
`ACCEPTED` vereist minstens 1,2× winst op zowel de medianen als de grens tussen
het eerste kwartiel van het origineel en het derde kwartiel van het voorstel.
Deze meetregel is indicatief voor de gebruikte testdata en meetomgeving.

Beide flags én browserbevestiging worden server-side gecontroleerd. Een flag is
een operatorverklaring: software kan daarmee niet bewijzen dat een URI werkelijk
geen productieomgeving is. Configureer deze POC daarom uitsluitend voor een
geïsoleerd testdoel en bind hem lokaal, zonder publieke toegang.

## Testen

De backendsuite gebruikt standaard offline testgrenzen. Voor de aanvullende
PostgreSQL-tests stel je `SUE_SYNTHETIC_TEST_DSN` in op een reeds gevulde,
wegwerpbare testdatabase met de synthetische fixture. De tests gebruiken echte
psycopg-transacties en één echte worker. Het modeltransport in deze suite is
gesimuleerd.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

### Historische dashboardcontrole

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

Historische artefacten tonen het oordeel en de meetmethode van hun oorspronkelijke
run. Nieuw correctheidsbewijs geldt voor de geteste parameters en database.

Echte workloadmonitoring/import, algemene query-equivalentie, automatische
indexcreatie, publieke authenticatie en een production optimizer blijven buiten
scope. De gebruiker ontvangt advies, geen automatisch toegepaste optimalisatie.

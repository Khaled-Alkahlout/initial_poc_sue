# Integratie in een bestaande backend

De bestaande UI kan haar eigen invoer en resultaatweergave behouden. De bruikbare Python-ingangen staan in `src/llm/`, `src/validator/` en `src/ui/pipeline.py`. Bij de overdracht zijn de importpaden en het gedrag van de POC behouden. Zie [ASSESSMENT.md](ASSESSMENT.md) voor de correcties die nodig zijn voordat een acceptatiebesluit gevolgen krijgt.

## Afhankelijkheden

Maak `src/` de importroot. Bijvoorbeeld `from llm.client import call_llm` en `from validator.checker import compare`. De oorspronkelijke mappen zijn namespacepackages zonder `__init__.py`. De CLI-scripts voegen `src/` zelf toe aan `sys.path`. Geef de modules bij definitieve inbouw een eigen namespace als het doelproject al mappen zoals `ui`, `scripts` of `llm` gebruikt.

Het oorspronkelijke `requirements.txt` geeft voor alle zeven packages alleen een naam of extra. Er zijn in de broncheckout geen lockfile of vastgelegde packageversies aangetroffen. Onderstaande testversies zijn de daadwerkelijk gebruikte versies voor deze overdracht.

| Oorspronkelijke specificatie | Gebruik in de POC | Versie bij verificatie |
| --- | --- | --- |
| `psycopg[binary]` | PostgreSQL-verbindingen, parameterbinding, transacties en fouttypes | `psycopg` 3.3.9, `psycopg-binary` 3.3.9 |
| `sqlglot` | PostgreSQL-AST voor de statische check en extractie van tabel- en kolomnamen | 30.32.0 |
| `anthropic` | Messages SDK, alleen geïmporteerd voor direct Anthropic-verkeer | 2.9.0 met transitief `httpx2` 2.16.2 |
| `pgserver` | Ingebedde PostgreSQL in demo en start-/stopscripts | Niet gebruikt, een geïsoleerde native server was beschikbaar |
| `streamlit` | Weergave en sessiestatus van de originele UI | Niet nodig voor het pakket |
| `pandas` | Resultaattabellen in de originele UI | Niet nodig voor het pakket |
| `matplotlib` | Grafieken uit experimentbestanden | Niet nodig voor het pakket |

Python 3.12 is de oorspronkelijke aanbeveling, mede wegens de Windows-wheels van `pgserver`. De overdracht is getest op Windows met Python 3.12.2 en PostgreSQL 16.2. OpenRouter gebruikt `urllib.request` uit de standaardbibliotheek. Wie uitsluitend OpenRouter of `mock` aanroept, heeft alleen `psycopg[binary]` en `sqlglot` nodig voor de volledige validatieroute. De directe Anthropic-client en de SDK-test gebruiken `anthropic`.

## Configuratie en geheimen

| Instelling | Waar de bestaande code die leest |
| --- | --- |
| Database-URI of psycopg-conninfo | Als parameter `uri` van `ui.pipeline.connect` of als eerste positieargument van de CLI. In de oorspronkelijke Streamlit-app kwam de waarde uit het URI-veld, uit `SUE_DEMO_DB_URI` als beginwaarde, of uit `pgserver.get_uri()`. |
| `OPENROUTER_API_KEY` | `llm.client._call_openrouter` leest het procesmilieu en zet een bearer-header. |
| `ANTHROPIC_API_KEY` | `llm.client._call_anthropic` controleert het procesmilieu en maakt `anthropic.Anthropic()`. De SDK leest de sleutel. |
| `OPENROUTER_BASE_URL` | Optionele override van `https://openrouter.ai/api/v1`. De code voegt `/chat/completions` toe. Laat de variabele weg voor de standaardwaarde. |

`SUE_DEMO_DB_URI` wordt in de bronkopie alleen gebruikt als een caller de waarde expliciet doorgeeft. Er is geen dotenv-loader of eigen secret store. De gebruikte Anthropic-SDK kent ook `ANTHROPIC_BASE_URL` als override. Houd DSN's, providerkeuze, API-sleutels en endpointoverrides in de backendconfiguratie. Een DSN met wachtwoord in een CLI-argument kan via shellgeschiedenis of de proceslijst zichtbaar worden. De verificatie gebruikte een verbindingsstring zonder wachtwoordargument en een tijdelijk wachtwoord via het procesmilieu.

`pipeline.connect(uri)` opent met `autocommit=True`, `connect_timeout=5` en doet `SELECT 1`. De batchrunners openen rechtstreeks met `psycopg.connect(uri, autocommit=True)` en stellen zelf geen connect-time-out in. Beheer in de doelbackend de levensduur en sluit de verbinding na gebruik, bijvoorbeeld met een contextmanager. Geef de huidige functies een eigen, inactieve autocommit-verbinding per taak. Een bestaande transactie kan betekenen dat `conn.transaction()` een savepoint gebruikt. Taken op een gedeelde verbinding delen ook de transactiestatus. [Psycopg-transacties](https://www.psycopg.org/psycopg3/docs/basic/transactions.html), [concurrent gebruik van verbindingen](https://www.psycopg.org/psycopg3/docs/advanced/async.html).

## Invoer en bestaande uitvoerpaden

`Case(name, original, order_cols, params, timing_params, candidates=[])` beschrijft één originele query. `ctx` is het object dat de twee parameterfuncties verwachten. Voor eigen casussen mag de caller dit zelf opbouwen.

| Veld | Verwachte invoer |
| --- | --- |
| `original` | PostgreSQL-SQL met benoemde psycopg-placeholders zoals `%(tenant_id)s`. Bind getypeerde waarden via de parametermapping. Een letterlijk procentteken in SQL die met parameters wordt uitgevoerd krijgt `%%`. |
| `order_cols` | Lijst met geordende namen van geretourneerde kolommen volgens de sorteervereisten, of `None` wanneer rijvolgorde geen deel uitmaakt van het contract. De code leidt dit niet af uit de SQL. |
| `params(ctx)` | Lijst met `(label, dict)` voor de correctheidsproeven. Lever een niet-lege set met unieke labels, randgevallen en de timingparameters. De POC dwingt dit niet af. |
| `timing_params(ctx)` | Eén dict voor `EXPLAIN ANALYZE` en de herhaalde vergelijking. |
| `Candidate(name, sql, expected, fault)` | De kandidaat-SQL. `expected` en `fault` zijn testlabels. Bij de batchroute krijgt een modelantwoord `unknown` en `llm`. De labels beïnvloeden het oordeel niet. |

`cases.cases` laadt de vier SQL-bestanden bij import. `make_ctx` groepeert de tabel `orders` op tenant en gebruikt min/max van `created_at` voor de grootste en kleinste groep. Het maakt brede, recente, lege en bovengrensvensters. Het recente venster is gebaseerd op de laatste order. `top_products` en `revenue_orders` gebruiken elk acht combinaties, `top_customers` vier en `audit_log_page` acht met variaties op tabelfilter en offset. De auditcasus vult `row_id` altijd met `None`. Bij `top_customers` zit de timingcombinatie `big/full` buiten de vier correctheidscombinaties.

### Streamlit-route in het oorspronkelijke project

`ui/app.py` kiest het origineel uit `CASES` en verzamelt bron, provider, model, effort, contextconditie, tokenlimiet en benchmarkrepetities. Eigen SQL kan als kandidaat worden geplakt. `_open` en `get_ctx` cachen verbinding en databasecontext per URI. `execute` doet voor live- of mockbron `build_prompt_for → ask_model`. De replayroute leest een opgeslagen SQL-antwoord. Handmatige kandidaten leveren SQL direct aan. Vervolgens roept `execute` de headless functies `static_check → check_equivalence → check_timing → decide` aan en bewaart de details in Streamlit-sessiestatus. De mutatietab gebruikt rechtstreeks `evaluate` uit het batchpad. Het overdrachtspakket bevat de headless functies, inclusief `run_all` als één aanroep voor validatie van al bekende kandidaat-SQL.

### Batchroute in het overdrachtspakket

1. `scripts/run_llm.py` leest de flags, maakt een uitvoermap en opent PostgreSQL. `make_ctx` wordt ook aangeroepen voor `C1_query` en `--dry-run`.
2. Per gekozen casus en conditie bouwt en bewaart de runner één prompt. Voor elke modelherhaling roept hij `call_llm` aan en haalt hij SQL uit het antwoord. `--dry-run` eindigt na de contextopbouw. `--model mock` volgt de rest van het pad met een SQL-echo.
3. Een modelcall-exceptie wordt normaliter `API_ERROR`. Bij `max_tokens` zonder gesloten codeblok wordt het `TRUNCATED`. Voor overige antwoorden maakt de runner een `Candidate` en roept hij `scripts.run_validation.evaluate` aan.
4. `evaluate` checkt alleen de kandidaat statisch. Per parameterset voert het de originele query en de kandidaat via `run_query` uit. Het kan originele resultaten uit de globale cache nemen. `compare` beoordeelt de kolommen, multiset en gegeven sorteersleutels. Alleen bij geaccepteerde vergelijkingsstatussen volgt `measure` op de timingparameters.
5. De runner schrijft instellingen naar `meta.json`, systeemprompt en prompts naar `prompts/`, ruwe antwoorden inclusief gebruik naar `responses/`, en oordelen naar JSONL, JSON en CSV. `llm.uitvoer` maakt het leesbare `resultaten.csv`. Standaard staat de uitvoermap onder `src/results/`. Gebruik `--out` met een nieuwe map om dit expliciet te sturen.

`run_experiment.py` gebruikt `resolve` om modelnamen naar provider-ID's om te zetten en roept `run_llm.py` per model en limiet als subprocess aan. `--plan` toont de vooraf ingestelde schatting. `--check` doet kleine echte modelrequests zonder database en test daardoor bereikbaarheid, zonder bewijs van de toegepaste reasoninginstelling. Hervatten gebeurt per model en limiet op basis van de aanwezigheid van `llm-results.csv`. De hervattingscontrole vergelijkt enkele runinstellingen, zonder database-identiteit of snapshot te controleren. Het experiment en de CSV-uitvoer zijn POC-gereedschap. De integratie kan rechtstreeks de functies aanroepen.

## Prompt en database-informatie

De contextcondities zijn cumulatief. `tables_and_columns` gebruikt sqlglot om tabelnamen en kolomnamen te zoeken en laat gevonden CTE-aliassen weg. `build_prompt` verpakt de blokken als tekst. `SYSTEM` vraagt om één equivalente PostgreSQL 16-query met dezelfde parameters en een korte uitleg in tekst na het SQL-codeblok. De modelstap heeft één aanroep en geen apart analyseantwoord.

| Conditie | Inhoud die de provider ontvangt | Databasewerk |
| --- | --- | --- |
| `C1_query` | Volledige originele SQL, inclusief commentaar en eventuele inline literals | Lokale parsing. De batch- en demoroute halen los daarvan parameters op. |
| `C2_schema` | Ook tabel- en kolomnamen, datatypes, nullability, constraint- en indexdefinities | `information_schema.columns`, `pg_constraint`, `pg_indexes` |
| `C3_plan` | Ook het tekstplan met tijden, aantallen, buffers en filters. Filters kunnen de gebonden parameterwaarden tonen. De tekst wordt na circa 8.000 tekens afgekapt. | `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)` voert het origineel uit met `Case.timing_params(ctx)`, in een read-only transactie met rollback en een standaardtimeout van 120 seconden. [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/16/sql-explain.html). |
| `C4_stats` | Ook geschatte aantallen rijen/pagina's en per gevonden kolom null-fractie, `n_distinct`, correlatie, frequente waarden en hun frequenties | `pg_class` en `pg_stats`. `most_common_vals` kan daadwerkelijke databasewaarden bevatten. Afkappen verkleint de tekst en verwijdert de gegevens niet. |

De validatierijen zelf blijven in het Python-proces. OpenRouter ontvangt de prompt als tussenpartij en routeert die door naar een modelendpoint. Voor de doelbackend moeten SQL-literals en commentaar, schema, plan en statistieken een expliciet gegevensbeleid krijgen. Volledige prompts, providerfoutteksten en antwoorden uit de CLI-instrumentatie horen buiten de normale applicatielogging.

## Model- en reasoninginstellingen

`call_llm(prompt, model, max_tokens=4000, original_sql="", provider="anthropic", effort=None)` gebruikt een provider-ID. De demo en batchrunner kiezen standaard OpenRouter. `run_llm.py` heeft een OpenRouter-model-ID als vaste default, dus geef bij `--provider anthropic` ook expliciet de directe model-ID op. De experimentele aliases `haiku`, `sonnet`, `opus` en `fable` staan in `MODEL_IDS` en de demokeuzes in `pipeline.MODELS`. De code bevat bijvoorbeeld `anthropic/claude-sonnet-5.5` voor OpenRouter en `claude-sonnet-5-5` voor Anthropic.

| Provider | Uitgaand request, lokaal bevestigd | Gebruik dat terugkomt uit de adapter |
| --- | --- | --- |
| OpenRouter | `POST /chat/completions` met `model`, `max_tokens`, systeem- en gebruikersbericht, `usage: {"include": true}`. Bij ingestelde effort ook `reasoning: {"effort": effort, "exclude": true}`. Bij `None` ontbreekt het hele reasoningobject. | `text`, `input_tokens`, `output_tokens`, `stop_reason`, `cost_reported` en het volledige `usage_raw`. Eventuele `completion_tokens_details.reasoning_tokens` blijft beschikbaar. |
| Anthropic direct | `POST /v1/messages` via de SDK. `model`, `max_tokens`, `system` en `messages` met optioneel `output_config.effort`, via `extra_body` toegevoegd. Bij `None` stuurt de code geen effort. Er wordt geen `thinking`-veld gezet. | Alleen tekstblokken. `usage_raw` bevat uitsluitend input- en outputtoken-aantallen. Aanvullende usagevelden zoals cachetokens gaan verloren. `cost_reported` is `None`. |

Beide adapters geven `seconds` terug. De CLI accepteert `low`, `medium`, `high`, `xhigh` en `max`. De catalogus en het gekozen endpoint bepalen welke waarden werken en welke thinkingstandaard geldt. Anthropic documenteert deze effort-niveaus voor de vier Claude-modellen in de POC. Bij OpenRouter kan een upstream endpoint onbekende parameters negeren onder standaardrouting. De POC stelt `provider.require_parameters` niet in en bewaart de feitelijke route niet. De Chat Completions-documentatie noemt `max_tokens` verouderd en noemt `max_completion_tokens` als opvolger. De kopie bewaart het oorspronkelijke request. [Anthropic effort](https://platform.claude.com/docs/en/build-with-claude/effort), [Anthropic thinking](https://platform.claude.com/docs/en/build-with-claude/thinking), [OpenRouter reasoning](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens), [OpenRouter routing](https://openrouter.ai/docs/guides/routing/provider-selection#requiring-providers-to-support-all-parameters), [OpenRouter Chat Completions](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion).

`pipeline.ask_model` voegt `sql`, `truncated` en `cost_usd` toe. De kosten zijn het gerapporteerde bedrag indien aanwezig, anders een schatting uit de historische prijstabel. Houd in de doelbackend aangevraagde instellingen, beschikbare gebruiksmetadata en kostenbron apart beschikbaar voor verantwoording. De code verwerkt geen verborgen redeneerstappen.

## Uitvoer en betekenis van de beslissingen

`pipeline.run_all(conn, case, ctx, sql, reps)` levert `static=(ok, detail)`, `equivalence`, `timing` en `verdict`. Een equivalentierij bevat `set`, `status`, `detail`, `orig_rows`, `cand_rows`, `orig_ms` en `cand_ms`. `evaluate(conn, case, cand, ctx, reps)` geeft een platte rij met labels, aantallen gefaalde sets, `flagged_not_equivalent` en indien gemeten dezelfde timingvelden. De benchmark levert beide medianen, beide IQR's, `speedup`, `faster` en het werkelijk gebruikte aantal `reps`.

| Uitkomst | Voorwaarde in de POC |
| --- | --- |
| `REJECTED_STATIC` | Parser of AST-check wijst de kandidaat af. |
| `REJECTED_NOT_EQUIVALENT` | Minstens één geteste set heeft een andere status dan `EQUIVALENT` of `TIE_AMBIGUOUS`. Ook `EXEC_ERROR` valt hieronder. |
| `EQUIVALENT_NOT_FASTER` | De vergelijkingsstatussen passeren en de snelheidsratio blijft onder 1,2. `pipeline.decide` gebruikt dit ook wanneer timing ontbreekt. |
| `ACCEPTED` | De kandidaat passeert de statische check, alle vergelijkingsstatussen tellen als geslaagd en de gemeten verhouding bereikt 1,2. De lege-setfout en tie-fout kunnen die uitkomst ook geven. |
| `TRUNCATED` / `API_ERROR` | Afzonderlijke batchstatussen vóór validatie. De oorspronkelijke UI behandelt deze gevallen anders. |

## Aansluiten op de eigen UI

1. Maak een server-side aanroep die originele SQL, sorteereisen en representatieve parametercombinaties ontvangt. Gebruik `Case` als startpunt en houd `CASES` en `make_ctx` bij de demo en tests.
2. Haal de DSN op uit de bestaande backendconfiguratie. Gebruik een taakgebonden verbinding met beperkte rechten op een testomgeving of geschikte replica. Pas een gecontroleerd uitvoeringsbeleid toe op origineel én kandidaat. Voer die controle ook uit voordat plancontext het origineel uitvoert.
3. Roep `build_context → build_prompt → call_llm → extract_sql` aan voor modelgedreven herschrijving. Valideer model en effort bij de gekozen provider en beoordeel welke contextblokken naar die provider mogen. Een rechtstreeks ingevoerde kandidaat kan de modelstap overslaan.
4. Breng `run_all` en `evaluate` uiteindelijk samen in één validatiepad. Maak ontbrekende en mislukte proeven expliciet, zet een consistente snapshot op voor beide queries, herstel de vergelijker en gebruik een benchmarkprotocol met een voldoende stabiele baseline. De aangetoonde fouten en testdekking staan in [ASSESSMENT.md](ASSESSMENT.md).
5. Lever aan de UI de kandidaat, teststatus per parameterset, timing en beschikbare modelmetadata. Behandel `ACCEPTED` voorlopig als een experimenteel oordeel op de gemeten steekproef. De POC heeft geen uitvoerpad dat de SQL automatisch vervangt.

Voor een lokale herhaling van de geteste batchpaden zie [tests/README.md](tests/README.md).

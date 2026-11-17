# Bronmanifest

De paden in de linker kolom zijn relatief aan de oorspronkelijke repository op commit `867d1d3377a050727d4c948be5e13a9268e1b5a5`. De paden in de pakketkolom zijn relatief aan deze map. Alle bestanden onder `src/` zijn ongewijzigde kopieën. Interne Python-imports behouden daardoor hun oorspronkelijke paden.

| Oorspronkelijk bestand | Relevante symbolen | Bestand in het pakket | Afhankelijkheden |
| --- | --- | --- | --- |
| `validator/checker.py` | `static_check`, `PLACEHOLDER`, `FORBIDDEN`, `run_query`, `compare` | `src/validator/checker.py` | sqlglot met PostgreSQL-dialect, open psycopg-verbinding, `Result`, `Comparison`, `norm_row` |
| `validator/normalize.py` | `norm_value`, `norm_row` | `src/validator/normalize.py` | Standaardbibliotheek `decimal`, `datetime`, `json` |
| `validator/classes/result.py` | `Result(columns, rows, ms)` | `src/validator/classes/result.py` | `dataclasses` |
| `validator/classes/comparison.py` | `Comparison(status, detail)` | `src/validator/classes/comparison.py` | `dataclasses` |
| `validator/timing.py` | `measure`, `TIMEOUT_MS`, `SPEEDUP_THRESHOLD` | `src/validator/timing.py` | `run_query`, `statistics`, PostgreSQL |
| `cases/classes/case.py` | `Case` | `src/cases/classes/case.py` | `dataclasses`, `Candidate` |
| `cases/classes/candidate.py` | `Candidate` | `src/cases/classes/candidate.py` | `dataclasses` |
| `cases/cases.py` | `CASES`, `original`, `make_ctx`, `std_params`, `std_timing`, `tc_params`, `audit_params`, `audit_timing`, `ro_params`, `ro_timing`, vier lijsten met mutaties | `src/cases/cases.py` | `Case`, `Candidate`, onderstaande SQL-bestanden, PostgreSQL-tabel `orders` voor `make_ctx` |
| `cases/original/top_products.sql` | `top_products` | `src/cases/original/top_products.sql` | `orders`, `order_lines`, `product_variants`, `products` |
| `cases/original/top_customers.sql` | `top_customers` | `src/cases/original/top_customers.sql` | `customers`, `orders` |
| `cases/original/audit_log_page.sql` | `audit_log_page` | `src/cases/original/audit_log_page.sql` | `audit_log`, benoemde parameters met optioneel `table_name` en `row_id` |
| `cases/original/revenue_orders.sql` | `revenue_orders` | `src/cases/original/revenue_orders.sql` | `orders` |
| `llm/context.py` | `CONDITIONS`, `tables_and_columns`, `schema_text`, `plan_text`, `stats_text`, `_short`, `build_context` | `src/llm/context.py` | sqlglot, PostgreSQL-catalogi en psycopg-verbinding, `Case.timing_params` |
| `llm/client.py` | `SYSTEM`, `HEADERS`, `PROVIDERS`, `SQL_BLOCK`, `build_prompt`, `extract_sql`, `call_llm`, `_call_openrouter`, `_post_json`, `_call_anthropic` | `src/llm/client.py` | `urllib` en `json` voor OpenRouter, luie import van `anthropic` voor directe Anthropic, API-sleutel per provider |
| `llm/prices.py` | `PRICES`, `LABELS`, `ORDER`, `family`, `cost_usd` | `src/llm/prices.py` | Standaardbibliotheek, historische tarieven in code |
| `llm/uitvoer.py` | `maak_rij`, `schrijf_resultaten_csv`, `voeg_samen` | `src/llm/uitvoer.py` | `llm.prices`, `SPEEDUP_THRESHOLD`, `csv`, `json`, door de batchrunner geschreven bestanden |
| `scripts/run_validation.py` | `main` (bestaande mutatietest), `evaluate`, `CACHE`, `OK_STATES`, `TIMEOUT_MS` | `src/scripts/run_validation.py` | psycopg, casussen, `static_check`, `run_query`, `compare`, `measure` |
| `scripts/run_llm.py` | `main`, `_append`, `EFFORTS` | `src/scripts/run_llm.py` | psycopg, casussen, context en client, `evaluate`, `schrijf_resultaten_csv` |
| `scripts/run_experiment.py` | `MODEL_IDS`, `resolve`, `plan_runs`, `estimate`, `check`, `main` | `src/scripts/run_experiment.py` | Casussen, context, client, prijstabel, CSV-helper, `subprocess` voor `run_llm.py` |
| `ui/pipeline.py` | `MODELS`, `connect`, `case_by_name`, `param_table`, `build_prompt_for`, `ask_model`, `check_equivalence`, `equivalent`, `check_timing`, `decide`, `run_all`, `stored_answers`, `load_answer` | `src/ui/pipeline.py` | psycopg, casussen, context en client, prijstabel, `OK_STATES` en `TIMEOUT_MS`, validator, optioneel gearchiveerde antwoordbestanden |

## Toegevoegd voor de overdracht

| Bestand | Herkomst en functie |
| --- | --- |
| `README.md`, `ASSESSMENT.md`, `INTEGRATION.md`, `MANIFEST.md` | Nieuwe overdrachtsdocumentatie |
| `requirements.txt` | Relevante, ongepinde requirements uit het oorspronkelijke `requirements.txt`. Het volledige oorspronkelijke overzicht staat in [INTEGRATION.md](INTEGRATION.md#afhankelijkheden). |
| `.env.example` | Veilige voorbeelden op basis van `llm/client.py` en de URI-instelling in `ui/app.py` |
| `tests/test_llm.py`, `tests/test_validator.py` | Nieuwe offline verificatie met `unittest`, transportstubs en synthetische rijen. De validatortests laden ook de bestaande casussen. |
| `tests/fixtures/synthetic.sql` | Nieuw klein schema en verzonnen rijen afgeleid van de interface van de vier originele query's. |
| `tests/README.md` | Instructies voor de offline tests en bestaande mutatie- en A/A-runners |

## Overige oorspronkelijke onderdelen

| Bestand of map | Rol in de POC |
| --- | --- |
| `ui/app.py` | Streamlit-UI met `execute`, `_open`, `get_conn`, `get_ctx` en `start_embedded_db`. De database- en validatieaanroepen die de nieuwe UI nodig heeft staan in `src/ui/pipeline.py`. |
| `scripts/start_db.py`, `scripts/stop_db.py` | Levenscyclus van de ingebedde pgserver-database van de demo. De overdracht verwacht een bestaande PostgreSQL-verbinding of een afzonderlijke testdatabase. |
| `scripts/analyse.py`, `scripts/analyse_models.py`, `scripts/grafieken.py` | Analyse en visualisatie van eerdere experimentresultaten buiten de online optimalisatieflow. De afsluithint van de gekopieerde experimentrunner blijft naar het oorspronkelijke analysescript verwijzen. |
| `results/` | Historische prompts, ruwe antwoorden, beoordelingen en figuren. De beoordeling gebruikt uitsluitend geaggregeerde observaties uit dit archief. |

De onderdelen in deze laatste tabel zijn uitgesloten van de bronkopie.

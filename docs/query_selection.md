# Query Filtering & Prioritization

## Doel en gebruik

Selectie gebeurt vóór contextopbouw en modelcalls. Daardoor veroorzaken
uitgesloten query's geen onnodige schema-opvragingen, profiling of modelkosten.
De module bepaalt geschiktheid en prioriteit voor **analyse**, niet of gegenereerde
SQL veilig mag worden uitgevoerd.

```powershell
python scripts/run_llm.py --selection-only --top-k 1
python scripts/run_llm.py --selection-only --exclude-query top_products --top-k 2
python scripts/run_llm.py --selection-only --exclude-table public.audit_log
```

Deze route vereist alleen Python en de bestaande dependency `sqlglot`:

```powershell
python -m pip install sqlglot
python -m unittest discover -s tests -v
```

Geen API-key, psycopg, PostgreSQL, pgserver, AWS of Anthropic SDK nodig. Er wordt
geen verbinding geopend, geen parameterfunctie aangeroepen en geen bestand
geschreven. Zonder selectievlaggen blijft de bestaande CLI-workflow intact.

## Inputcontract: QueryTelemetry

`query_selection/models.py` definieert één immutable dataclass per geaggregeerd
querypatroon. De module neemt geen raw events of cumulatieve snapshots samen.

| Veld | Type | Betekenis |
|---|---|---|
| `query_id` | `str` | Stabiele, binnen de aangeleverde bron-/databasescope unieke identiteit; bij fixtures `Case.name` |
| `sql` | `str` of `None` | Originele SQL, ongewijzigd bewaard, inclusief literals en placeholders |
| `calls` | `int` of `None` | Aantal uitvoeringen in het meetvenster |
| `mean_execution_time_ms` | `float` of `None` | Gemiddelde duur in datzelfde venster; intwaarden worden ook geaccepteerd |
| `total_execution_time_ms` | `float` of `None` | Totale duur in datzelfde venster |
| `source` | `str` | Expliciete provenance, bijvoorbeeld `mock:case-workload-v1` |
| `is_synthetic` | `bool` | Of de metingen fictief zijn |
| `window_id` | `str` of `None` | Identificeert het gezamenlijke meetvenster; verplicht voor afleiding van een ontbrekend totaal |
| `dialect` | `str` | Momenteel uitsluitend `postgres` |

De adapter garandeert dat metrics binnen één record hetzelfde venster beschrijven
en dat records in één ranking vergelijkbare observatieperiodes/databasescope
hebben. Eén `window_id` legt dit contract vast; de filterlaag kan niet bewijzen
dat een bron de cijfers daadwerkelijk over die periode heeft gemeten.

Er is geen SQL-equivalence-engine of algemene fingerprint toegevoegd. Identiteit
komt uit de adapter. SQL wordt alleen voor de eligibilitycontrole geparsed;
de oorspronkelijke tekst wordt niet herschreven of van literals ontdaan.

## Mockadapter en koppeling naar Cases

`mock_telemetry(cases)` in `query_selection/adapters.py` leest alleen kenmerken
van de bestaande objecten. De cijfers hieronder zijn bewust verzonnen en staan
los van alle benchmarkbestanden:

| Case / query-ID | Calls | Gemiddelde ms | Totale ms | Rang |
|---|---:|---:|---:|---:|
| `top_products` | 100.000 | 5 | 500.000 | 1 |
| `revenue_orders` | 1.000 | 10 | 10.000 | 2 |
| `audit_log_page` | 2.000 | 1,5 | 3.000 | 3 |
| `top_customers` | 1 | 2.000 | 2.000 | 4 |

Iedere rij heeft `source="mock:case-workload-v1"`, `is_synthetic=true` en
`window_id="synthetic-window-v1"`. Onbekende cases krijgen ontbrekende metrics,
geen verzonnen standaardbelasting, en worden uitgesteld.

`selected_cases(result, cases)` geeft dezelfde Case-objecten terug, in rangorde.
Er worden geen parameterfuncties of SQL gereconstrueerd. Ontbrekende cases,
dubbele casenamen of gewijzigde SQL geven een expliciete `ValueError`.

## Filteringregels

De beslisvolgorde is identiteit/deduplicatie, configureerbare queryuitsluiting,
SQL-geschiktheid en metrics. Een eerdere afwijzing kan een latere controle
overbodig maken; er wordt geen volledige lijst van alle mogelijke fouten beloofd.

| Situatie | Status | Redencode |
|---|---|---|
| Lege query-ID | `excluded` | `MISSING_QUERY_ID` |
| Zelfde ID en dezelfde SQL opnieuw | `excluded` voor latere records | `DUPLICATE_QUERY_ID` |
| Zelfde ID met verschillende SQL | Alle betrokken records `excluded` | `CONFLICTING_QUERY_ID` |
| ID uitgesloten in policy | `excluded` | `EXCLUDED_QUERY_ID` |
| SQL ontbreekt, is leeg of bevat alleen commentaar | `excluded` | `MISSING_SQL` |
| SQLGlot kan SQL niet parsen | `excluded` | `INVALID_SQL` |
| Ander dialect | `excluded` | `UNSUPPORTED_DIALECT` |
| Meer dan één statement | `excluded` | `MULTIPLE_STATEMENTS` |
| Geen ondersteunde SELECT, schrijf-CTE of SELECT INTO | `excluded` | `UNSUPPORTED_STATEMENT` |
| Expliciet uitgesloten schema of tabel | `excluded` | `EXCLUDED_SCHEMA` / `EXCLUDED_TABLE` |
| Ongeldige aanwezige metric | `excluded` | `INVALID_CALLS`, `INVALID_MEAN_EXECUTION_TIME_MS`, `INVALID_TOTAL_EXECUTION_TIME_MS` |
| Nul calls | `excluded` | `NO_EXECUTIONS` |
| Onvoldoende gegevens voor impact | `deferred` | `MISSING_TOTAL_EXECUTION_TIME_MS` plus ontbrekende secundaire velden |
| Totaal ontbreekt; calls/mean geldig maar venster ontbreekt | `deferred` | `MISSING_MEASUREMENT_WINDOW` |
| Afgeleide impact is niet eindig | `excluded` | `INVALID_DERIVED_TOTAL` |
| Geldig aangeleverd totaal | `eligible` | `PROVIDED_TOTAL` |
| Geldige afleiding | `eligible` | `DERIVED_TOTAL` |
| Wel geschikt, buiten top-k | `eligible`, niet geselecteerd | Aanvullend `OUTSIDE_TOP_K` |

SELECT-CTE's en SELECT-gebaseerde UNION/INTERSECT/EXCEPT worden ondersteund.
Statementcontrole is bewust geen garantie over functiegedrag of toegangsrechten.
Bijvoorbeeld `SELECT pg_sleep(1)` is geschikt als SELECT-vorm, maar selectie
geeft geen uitvoertoestemming.

Bij duplicates met dezelfde SQL wordt het eerste record behouden, ook als een
later record andere metrics heeft. Er wordt nooit gesommeerd of geprobeerd
snapshotsemantiek te raden. Alle latere records blijven zichtbaar in de output.
Adapters moeten één definitief aggregate per ID aanleveren.

Calls moeten niet-negatieve integers zijn; booleans en numerieke strings zijn
ongeldig. Tijden moeten eindige, niet-negatieve getallen zijn. Nul milliseconden
is een geldige duur. Een ontbrekende waarde is `None`, niet nul.

Als een geldig totaal aanwezig is, mogen calls of gemiddelde tijd ontbreken:
de query blijft rankbaar op totale impact. `MISSING_CALLS` en/of
`MISSING_MEAN_EXECUTION_TIME_MS` maken die beperking expliciet. Een aanwezige
maar ongeldige secundaire metric leidt wel tot uitsluiting.

## Prioriteringsmethode

Er zijn geen gewichten en geen minimumduur per uitvoering.

1. Gebruik `total_execution_time_ms` wanneer geldig aangeleverd.
2. Alleen als het totaal ontbreekt: gebruik `calls * mean_execution_time_ms`
   wanneer beide geldig zijn en een gezamenlijk `window_id` aanwezig is.
3. Sorteer op totale impact aflopend, gemiddelde tijd aflopend, calls aflopend,
   vervolgens query-ID oplopend.
4. Ontbrekende secundaire metrics komen na bekende waarden.
5. Ken alle geschikte records een 1-based rang toe; selecteer maximaal `top_k`.

Een aangeleverd totaal is leidend. De module reconcilieert geen afwijking tussen
dat totaal en `calls * mean` wanneer alle drie aanwezig zijn; bronafronding en
consistentie horen bij de adapter. `impact_source` en redencodes maken de keuze
zichtbaar. `top_k` verandert de impact of geschiktheid niet.

Dus 100.000 x 5 ms = 500.000 ms staat boven 1 x 2.000 ms = 2.000 ms.
De output bevat de gebruikte cijfers, herkomst van het totaal en rang, zodat
de prioriteit rechtstreeks kan worden verklaard.

## Configuratie: SelectionPolicy

| Instelling | Default | Betekenis |
|---|---|---|
| `top_k` | `None` | Alle geschikte query's; nul selecteert niets; negatief is ongeldige configuratie |
| `excluded_query_ids` | Leeg | Exacte query-ID's uitsluiten |
| `excluded_schemas` | `pg_catalog`, `information_schema` | Expliciet gekwalificeerde systeemobjecten uitsluiten |
| `excluded_tables` | Leeg | Tabelnamen of `schema.tabel` uitsluiten |

Objectnamen volgen PostgreSQL-spelling: ongequote identifiers worden lower-case,
gequote identifiers behouden hun case. CTE-aliassen worden niet als fysieke
tabellen behandeld. Zonder databaseverbinding kan een ongekwalificeerde tabel
niet via search_path aan een schema worden gekoppeld. Configureer daarvoor waar
nodig een expliciete tabeluitsluiting. Een lege `excluded_schemas` schakelt die
default in de Python-API uit; de CLI voegt `--exclude-schema` aan de defaults toe.

CLI: `--selection-only` impliceert mockselectie. `--select-mock` voert selectie
uit en vervolgt met de bestaande pipeline. `--top-k`, `--exclude-query`,
`--exclude-schema` en `--exclude-table` vereisen een selectiemodus. Uitsluitflags
zijn herhaalbaar. `--cases` begrenst vooraf de input; onbekende namen worden in
selectiemodus afgewezen. Een lege selectie retourneert JSON zonder services te
importeren of te verbinden, ook als een URI opgegeven is.

## Outputcontract en voorbeeld

`SelectionResult` bevat:

- `selected`: geselecteerde `QueryDecision`-objecten in prioriteitsvolgorde.
- `decisions`: één beslissing per inputrecord, in oorspronkelijke inputvolgorde.
- `policy`: de gebruikte configuratie.

Iedere beslissing bewaart het oorspronkelijke telemetryrecord, status,
`reason_codes`, `impact_ms`, `impact_source`, `rank` en `selected`.
`result.to_dict()` levert gewone JSON-types, zonder Case-callables of enums.
Niet-eindige/ongeldige numerieke input wordt in die JSON-weergave `null`, met
de bijbehorende invaliditeitscode; het oorspronkelijke object blijft bewaard
in `decision.telemetry`. Gebruik `json.dumps(..., allow_nan=False)`.

Zelfstandig voorbeeld (zonder Cases of services):

```python
import json
from query_selection.models import QueryTelemetry
from query_selection.policy import SelectionPolicy
from query_selection.selection import select_queries

records = [
    QueryTelemetry("fast", "SELECT 1", 100_000, 5, None,
                   "example:synthetic", True, "window-1"),
    QueryTelemetry("slow", "SELECT 2", 1, 2_000, 2_000,
                   "example:synthetic", True, "window-1"),
]
result = select_queries(records, SelectionPolicy(top_k=1))
print(json.dumps(result.to_dict(), indent=2, allow_nan=False))
print([(d.telemetry.query_id, d.impact_ms, d.rank, d.selected)
       for d in result.decisions])
# [('fast', 500000.0, 1, True), ('slow', 2000.0, 2, False)]
```

`fast` heeft `eligible`, `DERIVED_TOTAL`, `impact_source="calls_times_mean"`.
`slow` blijft `eligible` met `PROVIDED_TOTAL` en `OUTSIDE_TOP_K`.

Voor de bestaande cases levert `--selection-only --top-k 1` `top_products` op
met 500.000 fictieve ms. De andere drie cases blijven als geschikt maar buiten
het budget in `decisions` staan. In de echte runlogica wordt dit via
`selected_cases()` dezelfde `Case` als `CASES[0]`, met alle parameterfuncties.

## Later een echte bron aansluiten

Een nieuwe adapter levert `Iterable[QueryTelemetry]`. Hij is verantwoordelijk
voor database-/bronscope in de ID, eenheden, vergelijkbare meetvensters,
eventuele tellerresets en één definitief aggregate per ID. Zet
`is_synthetic=False` uitsluitend voor daadwerkelijk gemeten gegevens en gebruik
een herkenbare bronidentificatie. Filtering en ranking blijven onveranderd.

De huidige Case-resolver is specifiek voor bekende fixtures. Een echte collector
moet daarnaast een uitvoerbare query en veilige lokale parameterinformatie voor
context en tests beschikbaar maken. De huidige pipeline verwacht psycopg
`%(naam)s`-parameters; een workloadquery met `$1` is niet automatisch uitvoerbaar.
Een nieuwe ID of metadatarecord vervangt die testcontext niet.

## Grenzen en verificatie

Geen live monitoring, snapshotaggregatie, heranalysehistorie, algemene
query-equivalentie, automatisch indexbeheer of nieuwe safetyvalidator.
Correctheid en performance blijven afzonderlijke verantwoordelijkheden van de
bestaande validator, die in deze wijziging ongewijzigd is.

De tests controleren eligibility, uitsluitingen, ongeldige/ontbrekende metrics,
deduplicatie, ranking, budget, JSON, Case-identiteit en offline CLI-routing.
Orchestrationtests vervangen database/context/validator aan hun grenzen en
gebruiken het mockmodel. Ze bewijzen de koppeling en bestaande routecompatibiliteit,
niet dat een live databasebenchmark of externe provider werkt.

Gecontroleerd op 2 november 2026 met Python 3.13.7 en SQLGlot 30.27.0:
36 tests geslaagd. Twee afzonderlijke offline CLI-processen met dezelfde input
gaven identieke JSON-output. Psycopg, pgserver en de Anthropic SDK waren daarbij
niet geïnstalleerd; er is geen live database- of provider-run uitgevoerd.

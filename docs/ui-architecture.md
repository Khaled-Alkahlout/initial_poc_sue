# SUE INNO — UI-architectuur

## Doel en grenzen

Eén applicatie ondersteunt een begrijpelijke POC-demonstratie en technische
ontwikkeling. Het is een onderzoeksomgeving, geen autonome DBA. Bestaande
Python-logica blijft de bron van waarheid voor selectie, generatie en validatie.
Er zijn geen extra agent, feedbacklus, microservices of cloudafhankelijkheden.

De frontend gebruikt Next.js App Router, React, strict TypeScript en Tailwind.
De lokale UI-primitives volgen shadcn/ui-compositie: Button/Slot, Card, fields
en een toegankelijke Radix Dialog zijn lokaal aanpasbaar. Lucide verzorgt iconen,
Prism SQL-highlighting en Recharts de twee inhoudelijke grafieken.

## Datastroom

De [OpenRouter-flow](openrouter.md) gebruikt één pipeline voor analyse, een
volledige run en validatie van een opgeslagen voorstel.

```mermaid
flowchart TD
    Pages["Next.js App Router<br/>POC + Development"] --> Client["Typed API-client + Zod"]
    Client -->|"REST /api; lokale proxy"| Routes["FastAPI routes + Pydantic"]
    Routes --> Catalog["Catalog: read models"]
    Catalog --> Historical["Artifacts-adapter<br/>historische JSON + prompts/response"]
    Historical --> Results[("results/ · alleen-lezen")]
    Catalog --> Adapter["Bestaande mock_telemetry"]
    Adapter --> Selection["Bestaande query_selection<br/>filtering + impactranking"]
    Routes --> Queue["JobManager<br/>1 actief + 1 wachtend"]
    Queue --> Worker["Begrensd Python-workerproces"]
    Worker --> Selection
    Worker --> Check["Controle origineel"]
    Check --> Analysis["analysis/live: context → OpenRouter → Pydantic"]
    Analysis --> Proposal["Controle SQL-voorstel"]
    Check --> Saved["validate: opgeslagen voorstel"]
    Saved --> Proposal
    Proposal --> Store
    Proposal --> Validation["live/validate: validator/evaluation.py"]
    Worker --> Replay["Historische replay<br/>geen nieuwe meting"]
    Replay --> Historical
    Worker --> Offline["Expliciete mock en statische controle"]
    Analysis -->|"C2–C4 op een live run"| DB[("Bevestigde testdatabase")]
    Validation --> DB
    Validation --> Store
    Worker --> Store[(".local/dashboard.sqlite3<br/>nieuwe taken + JSON-resultaten")]
    Routes --> Feedback["Handmatige reviews"]
    Feedback --> Store
```

De live tak bestaat in code en wordt pas aangeboden wanneer serverconfiguratie
en dependencies aanwezig zijn. Die beschikbaarheid is geen bewijs van een
werkende verbinding of modelprovider. De demo heeft deze tak niet nodig.

## Modulestructuur

```text
api/
  app.py, config.py, routes.py, schemas.py, worker.py
  services/
    artifacts.py      # legacy parsing en conservatieve statusadaptatie
    catalog.py        # samengestelde query-, run- en evaluatieviews
    jobs.py           # begrensde processen en lifecycle
    workflows.py      # bestaande domeinfuncties combineren
    storage.py        # SQLite voor taken en reviews
    privacy.py        # redactie voor weergave en context
frontend/
  src/app/           # route-entrypoints, server-side data ophalen
  src/features/      # dashboard, queries, runs, development
  src/components/    # ui, layout, queries, pipeline, evaluation, charts, shared
  src/lib/api/       # één client, responsecontracten en datafoutafhandeling
  src/lib/config/    # centrale sidebar-navigatie
  src/hooks/         # lokale server-state en begrensde polling
  src/tests/         # component- en contracttests; geen productiedatabron
  e2e/               # echte lokale demo-smoketests
```

## Verantwoordelijkheden

| Grens             | Verantwoordelijkheid                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| Python-domein     | De bestaande selectie, context, modelcall en validator. Geen JS-kopie.                            |
| FastAPI           | Invoer valideren, bestaande functies aanroepen en typed HTTP-contracten aanbieden.                |
| Artifactadapter   | Ontbrekende data behouden als onbekend, provenance bewaren, legacy-statussen zorgvuldig vertalen. |
| API-client        | Fetch centraliseren en elke response met Zod valideren. Geen vervangende succesdata bij fouten.   |
| Domeincomponenten | Typed props renderen: SQL, fases, benchmark, context, matrix en reviews.                          |
| Features          | Componenten samenstellen en presentatie-interactie beheren.                                       |
| Routes            | Gegevens ophalen en feature kiezen; pagina's zijn onafhankelijk verwijderbaar.                    |
| Stijl             | CSS-variabelen, semantische statuskleuren en gedeelde primitives. Geen remote fonts nodig.        |

`api/schemas.py` is het HTTP-contract. De TypeScript/Zod-contracten in
`frontend/src/lib/api/contracts.ts` volgen dit expliciet. Bij contractwijzigingen
worden beide bijgewerkt; runtimevalidatie voorkomt dat afwijkende responses
stilzwijgend succesvolle waarden krijgen.

Server Components halen initiële data op. Client Components zijn beperkt tot
interactieve tabellen, charts, dialogs, SQL-copy, reviews en actieve-runstates.
Er is geen globale state manager. `useApi` pollt actieve taken; na voltooiing
stopt polling. Bij een fout is expliciete retry beschikbaar.

## Een replay starten via de API

```mermaid
sequenceDiagram
    actor User as Gebruiker
    participant API as FastAPI
    participant Queue as JobManager
    participant Worker as Python-worker
    participant Select as query_selection
    participant Artifacts as Historische artefacten
    participant Store as SQLite
    participant UI as Run Details
    User->>API: POST /api/runs met mode=replay, query_id en condition
    API->>API: Case, modus, bron en prerequisites controleren
    API->>Store: PENDING + gevalideerde configuratie
    API->>Queue: vaste operatie in begrensde queue
    API-->>User: 202 + run-ID
    User->>UI: Open run-ID in Analysehistorie
    Queue->>Worker: gegenereerde UUID, geen credentials in argv
    Worker->>Store: RUNNING
    Worker->>Select: mock_telemetry → select_queries → selected_cases
    Worker->>Artifacts: lees opgeslagen poging
    Artifacts-->>Worker: response, context, validator- en benchmarkvelden
    Worker->>Store: COMPLETED + resultaat met historische provenance
    loop Alleen zolang PENDING/RUNNING
        UI->>API: GET /api/runs/{id}
        API->>Store: lees status/resultaat
        API-->>UI: typed runcontract
    end
    UI-->>User: fases, SQL, metingen en beperkingen
    User->>UI: handmatige review
    UI->>API: POST feedback
    API->>Store: review apart opslaan
    Note over UI,Store: Technische resultaten blijven ongewijzigd; geen feedback naar het model
```

## Uitvoermodi en herkomst

| Modus               | Wat werkelijk gebeurt                                                                                                              |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Historisch          | Bestaande artefacten bekijken. Geen nieuwe uitvoering.                                                                             |
| Replay              | Nieuwe selectie en taakregistratie; historische response en metingen hergebruiken. Nul nieuwe modelrequests.                       |
| Offline mock        | C1-casus met een kopie van de originele SQL en statische controle.                                                                  |
| Testdatabase + mock | Dezelfde SQL aan beide kanten van de validator, als expliciete A/A-controle.                                                        |
| Live                | Gestructureerde OpenRouter-analyse gevolgd door validatie op de bevestigde testdatabase.                                             |
| AI-analyse          | Eén gestructureerd OpenRouter-request met de gekozen context. Metadata kan uit de bevestigde testdatabase komen. Het voorstel wordt opgeslagen. |
| Voorstelvalidatie   | Afzonderlijk opgeslagen voorstel testen na SQL-gates; geen nieuw modelrequest.                                                     |

Het startscherm biedt één SQL-analyse met twee afzonderlijke keuzes. **Context
voor het model** bepaalt de userprompt. **Na de analyse** bepaalt of correctheid
en performance worden getest. Alle SQL-modelaanroepen delen dezelfde
systeemprompt. Nieuwe dashboardresultaten bewaren beide verstuurde prompts.

Het Explorer-budget geldt voor de getoonde selectie. Een expliciete run kiest
één fixture en past top-1-selectie toe op die gekozen subset. Iedere run bewaart
zijn eigen selectiesnapshot. Er is geen verborgen globale beleidsinstelling.

Historische tokens en requestduur blijven historische informatie in een replay.
De run rapporteert daarnaast nul nieuwe modelrequests. Tijdzone-loze historische
bestandsdatums worden als bronkloktijd getoond, met onbekende tijdzone; nieuwe
taaktimestamps worden in UTC opgeslagen en in Europe/Amsterdam weergegeven.

## Statusmodel en bewijs

Processtatus is `PENDING → RUNNING → COMPLETED / FAILED`. Afgerond betekent
verwerking gereed, niet dat een voorstel goedgekeurd is. Annuleren is niet
aangeboden: er is geen veilige user-facing cancellation geïmplementeerd.

Fases onderscheiden pending, running, passed, failed, warning, inconclusive,
skipped en error. Ontbrekende fase-duren blijven onbekend; mediane querytijd
wordt niet als totale fase-duur hergebruikt.

- `TIE_AMBIGUOUS` wordt niet als bewezen correct of sneller getoond.
- `EXEC_ERROR` blijft een uitvoeringsfout, geen aangetoond resultaatverschil.
- Een legacy-afwijzing zonder bewijsdetails blijft onbeslist.
- Een benchmark leidt alleen tot een performanceconclusie bij voldoende
  geregistreerd correctheidsbewijs. Ontbrekende velden worden niet verzonnen.
- Het oorspronkelijke validatoroordeel blijft zichtbaar naast de interpretatie.
- Bij mutatietests wordt de validator vergeleken met het auteurslabel. Een
  correct afgewezen mutant is een geslaagde test, geen goedgekeurd voorstel.

Het huidige validatorpad vergelijkt kolomtypen, volledige rijen met multipliciteit
en de vereiste sorteervolgorde. Historische resultaten blijven voorzien van hun
eigen herkomst en meetmethode.

## Opslag en beveiligingsgrens

Historische `results/` blijven ongewijzigd; ze worden bij API-start ingelezen.
Na nieuwe externe CLI-experimenten is een API-herstart nodig om die bestanden
te importeren. Nieuwe dashboardtaken en reviews staan apart in `.local/`, dat
door Git wordt genegeerd. Reviews wijzigen nooit technische resultaatrecords.

Eén API-worker, één actief workerproces en één wachtende taak begrenzen de lokale
uitvoering. De taaklimiet is 300 seconden. Voor runs met SQL-validatie geldt
2 uur en 5 minuten voor maximaal drie vergelijkingsparen en drie benchmarkparen
met maximaal tien minuten per query. Een herstart markeert onderbroken
taken als mislukt; geen stilzwijgende hervatting. Alleen vaste cases en suites
zijn toegestaan. Processen gebruiken geen shell; credentials staan niet in argv.

Live DB-connecties hebben connect-timeout 5 s en een read-only default. Proeven
draaien in één snapshot met rollback, statement- en lock-time-outs en een
rijlimiet. Gebruik een geïsoleerde testdatabase met een beperkte SELECT-rol.
[Uitvoeringsgrenzen](openrouter.md#een-geïsoleerde-testdatabase-aansluiten)

Services binden lokaal. Hostcontrole, beperkte origins en gevalideerde JSON-invoer
beperken browsermisbruik. Er is geen authenticatiesysteem voor publieke hosting.
Secrets, URI's, e-mailadressen, UUID's, datumliterals en contextwaarden worden
beperkt in browserresponses; MCV-waarden worden verwijderd. Redactie is
conservatief en geen algemene DLP-garantie. Gebruik de synthetische testomgeving;
sluit gevoelige productiegegevens niet zonder afzonderlijke privacybeoordeling aan.

# Dashboard uitbreiden

## 1. Een pagina toevoegen

1. Maak een route onder `frontend/src/app/<route>/page.tsx`.
2. Haal serverdata via `api` en `loadPage` op; render JSX pas na de data-afhandeling.
3. Plaats featurelogica onder `src/features/<domein>/`.
4. Gebruik `PageHeader`, `Card` en passende domeincomponenten.
5. Voeg alleen bij interactie een Client Component toe.
6. Voeg desgewenst één item toe in `src/lib/config/navigation.ts`.
7. Test rendering, ontbrekende data en het navigatiepad.

De shell importeert geen featurepagina's. Toevoegen vereist geen layoutwijziging.

## 2. Een pagina verwijderen

Verwijder de route en zijn centrale navigatie-item. Zoek expliciete links naar
die route en verwijder of vervang die. Gedeelde componenten, API-contracten en
andere features hoeven niet te veranderen wanneer ze die pagina niet gebruiken.
Een niet-bestaande recordroute gebruikt de gezamenlijke not-found-weergave.

## 3. Sidebar wijzigen

Pas `src/lib/config/navigation.ts` aan: groep, label, href en Lucide-icon.
`AppShell` verzorgt actieve route, responsive menu en sluiting na navigatie.
Voeg geen menuconfiguratie toe aan afzonderlijke pagina's.

## 4. Een gedeelde component toevoegen

- Presentatieprimitive: `src/components/ui/`.
- Domeincomponent: `queries/`, `pipeline/` of `evaluation/`.
- Ontvang typed props uit de API-contracten.
- Geen raw fetch, scoremodel of equivalentiecontrole in een presentatiecomponent.
- Voeg toetsenbordgedrag, ontbrekende-data-weergave en betekenisvolle tests toe.

Een nieuwe `PerformanceComparison`-variant mag gemeten velden anders presenteren,
maar niet zelf besluiten of twee queries equivalent zijn.

## 5. Een API-endpoint toevoegen

1. Definieer Pydantic-invoer en -output in `api/schemas.py`.
2. Implementeer de operatie/read model in een passende service.
3. Hergebruik bestaande domeinfuncties; kopieer geen validator in routes.
4. Voeg een dunne route toe in `api/routes.py`.
5. Test ontbrekende records, ongeldige input, provenance en fouttoestanden.
6. Voeg het Zod-contract en een methode in `src/lib/api/client.ts` toe.
7. Gebruik de methode vanuit een serverpagina of `useApi`-loader.

Nieuwe uitvoeroperaties moeten expliciet in de server-allowlist komen, met
prerequisites en een begrensde worker. Accepteer nooit een commandostring,
bestandslocatie of vrije SQL uit de browser.

## 6. Een nieuwe testevaluatie visualiseren

Lever een `TestRecord` met echte verwachting (of `null`), werkelijke uitkomst,
status, provenance en beschikbare duur. Gebruik geen fictieve succesvelden.
De matrix kan automatisch op een nieuwe componentnaam filteren.
Voeg specifieke inspectie toe aan een eigen domeincomponent; de testdetailpagina
kan die naast de bestaande metadata en review tonen.

Een nieuwe uitvoerbare suite vraagt tevens een allowlist-entry in de catalog,
request-Literal en workeroperatie. Pas bij nieuwe testtypes ook het custom
unittest-resultaatprotocol aan; test failures, errors en skips afzonderlijk.

## 7. Een chart toevoegen

Maak een Client Component onder `src/components/charts/`, met typed props en
een toegankelijke beschrijving. Gebruik Recharts en een responsive container
met expliciete hoogte. Geef herkomst en eenheden aan. Bewaar beslislogica in
Python. Een chart zonder betrouwbare meetgegevens krijgt een lege toestand.

## 8. Styling wijzigen

Kleuren en statuspalet staan bovenaan `src/app/globals.css` als CSS-variabelen.
De donkere variant gebruikt dezelfde tokens. Gedeelde primitives verzorgen
buttons, velden, cards en dialogs. De shadcn-configuratie staat in
`frontend/components.json`; primitives blijven lokaal aanpasbaar.
Behoud tekst/iconen naast statuskleuren, focusindicaties en reduced-motion.
Controleer desktop en een klein viewport na visuele wijzigingen.

## 9. Mocktelemetrie vervangen

Maak een Python-adapter die hetzelfde bestaande `QueryTelemetry`-contract
levert. Garandeer scoped stabiele IDs, vergelijkbare meetvensters, eenheden en
één aggregate per ID. Zet `is_synthetic=False` alleen voor echte metingen.
Vervang de adapteraanroep in de catalog/workflowgrens; filtering en frontend
hoeven daardoor niet te veranderen.

De huidige runner ondersteunt uitsluitend bestaande Case-objecten. Een nieuwe
querybron moet daarom ook uitvoerbare SQL en veilige lokale parameterprofielen
kunnen leveren; een telemetry-ID alleen is onvoldoende om SQL te testen.
Neem die uitbreiding expliciet mee in de runner en test de safetygrens voordat
nieuwe bronnen uitvoerbaar worden. Voeg niet alvast een collector of cloudlaag toe.

## Provider vervangen

Houd providerwijzigingen aan de Python-generatiegrens. Behoud responsevelden
voor tekst, SQL-extractie, tokens, duur en onbekende waarden. De frontend kent
alleen die contracten en hoeft geen provider-SDK te importeren. Geen tweede
agent of automatische feedbacklus toevoegen als onbedoeld onderdeel hiervan.

# Verificatietests

De oorspronkelijke mutatietest staat in [src/scripts/run_validation.py](../src/scripts/run_validation.py). Hij gebruikt de vier originele [SQL-bestanden](../src/cases/original/) en 22 kandidaten uit [src/cases/cases.py](../src/cases/cases.py). Die bestanden staan op hun oorspronkelijke importlocatie in `src/` en vormen ook de testbank van de batch- en headless modules. De A/A-controle gebruikt `--model mock` in [src/scripts/run_llm.py](../src/scripts/run_llm.py).

## Offline

Installeer de requirements en voer vanuit `transfer_package/` uit.

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -B -m unittest discover -s tests -v
```

- `test_llm.py` controleert de prompt en SQL-extractie, de mock, de OpenRouter-JSON bij elk van de vijf effort-niveaus en de default, gebruiksmetadata, time-outargument, retry bij 429 en timeout, permanente fout, ontbrekende key en ongeldig antwoord. De Anthropic-test gebruikt de echte SDK met een mocktransport. Deze test wordt overgeslagen als het SDK-transport `httpx2` of de SDK ontbreekt.
- `test_validator.py` controleert statische acceptatie en afwijzing, reproduceert voorbeelden die de statische filter doorlaat en controleert transactiecommando's met een mock. De module controleert `NULL`, multipliciteit, kolommen, volgorde, de timingvolgorde en drempel, de fixturecatalogus en modelaliases. De tests leggen ook de gedragstekorten vast bij tie-grenzen, typen, schemaresolutie, nul parametersets en cachehergebruik tussen verbindingen.

De offline tests gebruiken geen echt database- of providertransport. De tests die een defect demonstreren verwachten de oorspronkelijke uitkomst. Werk deze verwachtingen bij zodra de doelbackend de fouten herstelt.

## Op een eigen tijdelijke PostgreSQL-testdatabase

Gebruik een nieuw aangemaakte, lege, wegwerpbare testdatabase die je zelf beheert. [fixtures/synthetic.sql](fixtures/synthetic.sql) voert DDL, inserts en `ANALYZE` uit. Alle gegevens in het bestand zijn verzonnen. Het initialiseert zes tabellen in `public` met onder meer duplicaten, `NULL` en gelijke audit-timestamps. De fixture is klein genoeg voor de aanwezige CLI-proeven.

Stel `SUE_DEMO_DB_URI` in voor deze tijdelijke database. Onderstaand voorbeeld geeft de waarde expliciet door aan psql en Python.

```powershell
$dsn = $env:SUE_DEMO_DB_URI
if (-not $dsn) { throw 'Geef de URI van de tijdelijke testdatabase op.' }
psql -X -v ON_ERROR_STOP=1 -d $dsn -f tests/fixtures/synthetic.sql
if ($LASTEXITCODE -ne 0) { throw 'Het laden van de synthetische fixture is mislukt.' }
python -X utf8 -B src/scripts/run_validation.py $dsn --reps 3
$out = Join-Path $env:TEMP ("sql-transfer-" + [guid]::NewGuid().ToString("N"))
python -X utf8 -B src/scripts/run_llm.py $dsn --dry-run --out (Join-Path $out dry)
python -X utf8 -B src/scripts/run_llm.py $dsn --model mock --reps 1 --val-reps 3 --out (Join-Path $out mock)
```

De mutatietest schrijft JSON en CSV naar `src/results/`. De dry-run bouwt alle 16 prompts en draait voor C3 en C4 ook `EXPLAIN ANALYZE`. De mockrun meet elke originele query tegen zichzelf. Ieder `ACCEPTED` in deze A/A-run is een foutpositieve tijdmeting. Concrete tijden en oordelen kunnen per herhaling variëren.

De uitkomsten van de uitgevoerde tests, de extra PostgreSQL-proeven en de batchproef met een OpenRouter-transportstub staan in [ASSESSMENT.md](../ASSESSMENT.md#verificatie-en-afbakening).

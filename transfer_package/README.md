# Overdrachtspakket SQL-optimalisatie

Dit pakket bevat de Python-backend van de PostgreSQL-POC, inclusief de prompt, contextopbouw, modelclients, validatie, tijdmeting en beslislogica. Het is bedoeld voor aansluiting op de bestaande UI van een ander project. De twintig bronbestanden onder `src/` zijn byte voor byte overgenomen uit de checkout op commit `867d1d3377a050727d4c948be5e13a9268e1b5a5`.

## Waar te beginnen

- [ASSESSMENT.md](ASSESSMENT.md) geeft per onderdeel het hergebruikadvies, de aangetoonde beperkingen en de testresultaten.
- [INTEGRATION.md](INTEGRATION.md) beschrijft de aanroepvolgorde, instellingen, afhankelijkheden, invoer en uitvoer.
- [MANIFEST.md](MANIFEST.md) wijst de oorspronkelijke paden, relevante functies en gekopieerde bestanden aan.
- [tests/README.md](tests/README.md) bevat de offline controles en instructies om de bestaande mutatietest en A/A-controle op synthetische data te draaien.
- [.env.example](.env.example) vermeldt de omgevingsvariabelen van de POC. De code leest het procesmilieu en laadt dit voorbeeldbestand niet in.

`src/ui/pipeline.py` is de headless laag achter de demo. De module importeert `psycopg` en de backendmodules en kan zonder Streamlit worden gebruikt. De vier oorspronkelijke SQL-casussen en de mutaties staan waar de scripts ze verwachten, onder `src/cases/` en `src/scripts/run_validation.py`. De nieuwe testfixture bouwt een klein synthetisch schema met rijen voor die casussen.

## Offline controleren

Gebruik een schone Python-omgeving. De oorspronkelijke documentatie beveelt Python 3.12 aan. De geteste versies staan in [INTEGRATION.md](INTEGRATION.md#afhankelijkheden).

```powershell
# Vanuit transfer_package/
python -m pip install -r requirements.txt
$env:PYTHONPATH = (Resolve-Path src).Path
python -B -m unittest discover -s tests -v
```

Op een POSIX-shell is het equivalent van de tweede regel `export PYTHONPATH="$PWD/src"`. De offline controles gebruiken synthetische providerresponses en hebben geen database, API-sleutel of netwerkverbinding nodig. Enkele controles leggen bekende fouten van de POC vast. Een geslaagde controle betekent dan dat het gedocumenteerde gedrag is gereproduceerd.

## Gecontroleerde reikwijdte

In een losstaande kopie zijn 17 offline controles geslaagd. Op een tijdelijke PostgreSQL 16.2-testdatabase zijn de mutatietest, contextopbouw C1–C4 en batchvalidatie met een SQL-echo en een OpenRouter-transportstub gedraaid. De providerrequests zijn ook onafhankelijk gecontroleerd op serialisatie van model, effort en tokenlimiet. Live gedrag bij Anthropic, OpenRouter of een doeldatabase blijft onbevestigd.

Gebruik de gekopieerde validator als POC. Voor verwerking van vrije SQL of gebruik van `ACCEPTED` als automatisch besluit zijn aanpassingen aan de toelatingscontrole, datadeling, resultaatvergelijking en benchmark nodig. De Streamlit-app, experimentresultaten, database-exports, databasecredentials en API-sleutels vallen buiten het pakket.

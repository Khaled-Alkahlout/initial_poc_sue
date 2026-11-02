# LLM-koppeling

Doel: meten welke contextinformatie het verschil maakt tussen een correcte en snellere herschrijving
en een foute of nutteloze. Elke LLM-uitvoer gaat door hetzelfde framework als `run_validation.py`.

## Bestanden

- `llm/context.py`: bouwt de context uit de database (read-only). Vier cumulatieve condities:
  - `C1_query`: alleen de originele query
  - `C2_schema`: + kolommen, constraints en indexen van de gebruikte tabellen
  - `C3_plan`: + `EXPLAIN (ANALYZE, BUFFERS)` van het origineel op de timing-parameters
  - `C4_stats`: + rijen per tabel en `pg_stats` (null_frac, n_distinct, correlation, meest voorkomende waarden)
- `llm/client.py`: systeemprompt, prompt opbouwen, Anthropic API aanroepen, SQL uit het antwoord halen
- `scripts/run_llm.py`: voert alles uit en beoordeelt elke herschrijving met `evaluate()` uit `run_validation.py`

## Installeren (eenmalig, in de conda-omgeving `deepdive`)

```
pip install anthropic
```
API-sleutel (van console.anthropic.com), alleen voor de huidige terminal:
- PowerShell: `$env:ANTHROPIC_API_KEY="sk-ant-..."`
- cmd: `set ANTHROPIC_API_KEY=sk-ant-...`

Zet de sleutel nooit in een bestand dat in git komt.

## Draaien (database moet draaien)

1. Prompts bekijken, zonder API en zonder kosten:
   `python scripts/run_llm.py "<URI>" --dry-run`
2. A/A-controle: de "LLM" geeft het origineel ongewijzigd terug. Elke `ACCEPTED` hier is meetruis.
   `python scripts/run_llm.py "<URI>" --model mock --reps 1`
3. Echte run (4 query's x 4 condities x 3 = 48 API-aanroepen):
   `python scripts/run_llm.py "<URI>" --model claude-sonnet-5-5 --reps 3`
   Kleiner beginnen kan met `--cases revenue_orders --conditions C1_query C3_plan --reps 1`.

Uitvoer: `results/llm-<tijdstempel>/` met
- `prompts/`: precies wat het model kreeg
- `responses/`: ruw antwoord, de eruit gehaalde SQL en het tokengebruik
- `llm-results.csv`: oordeel per herschrijving, met de kolommen `condition`, `rep`, `unchanged` en `speedup`

Onderaan de uitvoer staat per conditie hoeveel herschrijvingen statisch zijn afgekeurd, fout waren,
gelijk maar niet sneller waren, of zijn geaccepteerd.

## Bekende beperkingen

- `top_customers` duurt ongeveer 8 s per uitvoering. C3/C4 doen voor die query een extra `EXPLAIN ANALYZE`.
- De condities zijn cumulatief. Het effect van bijvoorbeeld alleen statistieken zonder plan wordt dus niet apart gemeten.
- Het framework kent geen "trager"-oordeel: een kandidaat met speedup < 1 heet `EQUIVALENT_NOT_FASTER`.
- In een A/A-test op synthetische data gaf een ongewijzigde query bij 3 tijdmetingen 2 van de 16 keer
  `ACCEPTED`, en bij 7 metingen 1 van de 32 keer. Draai stap 2 daarom ook op de echte data.

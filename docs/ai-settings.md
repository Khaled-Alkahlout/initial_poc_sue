# AI Settings en responsdiagnostiek

De pagina `/settings` beheert generatie-instellingen via FastAPI en de bestaande
lokale SQLite-opslag. De API-key, modelkeuze en SQL-veiligheidsflags blijven
serverconfiguratie. De browser schrijft nooit `.env`.

## Diagnose vóór de wijziging

In de aangetroffen nieuwe analyse waren 3865 inputtokens en 3644 outputtokens
geregistreerd. De gestructureerde uitleg bevatte 280 tekens; `optimized_sql` was
null. Dat betekent dat het model geen rewrite voorstelde, niet dat alle modeloutput
ontbrak. De workspace toonde opgeslagen resultaten na heropenen bovendien alleen
via een link. Die resultaten worden nu direct opnieuw geladen en weergegeven.

`llm/analysis.py:chat` gebruikte een vast maximum van 4000 en stuurde geen
reasoning-instelling. Bij een andere finish reason dan `stop` werd een algemene
exception opgegooid vóór bewaring van usage. Finish reason, reasoningtokens en
zichtbare lengte ontbraken daardoor in oude artifacts. Truncatie of een opgebruikt
reasoningbudget kan voor die oude antwoorden niet achteraf worden bewezen.

Dit is dus geen bewezen universeel tokenlimietprobleem. De wijziging lost het
verlies van diagnostiek en het verborgen blijven van opgeslagen resultaten op,
en maakt het budget daadwerkelijk configureerbaar.

## Instellingen en prioriteit

```dotenv
SUE_MAX_OUTPUT_TOKENS=4096
SUE_REASONING_EFFORT=low
```

Prioriteit: opgeslagen voorkeuren → environment defaults → bovenstaande ingebouwde
standaarden. Procesvariabelen blijven vóór `.env` gaan. Een save bewaart uitsluitend
`max_output_tokens`, `reasoning_effort` en `temperature` als JSON in de SQLite-tabel
`settings`. Nieuwe analyses krijgen bij enqueue een snapshot in hun taakconfiguratie.
Wijzigingen gelden voor volgende aanvragen, zonder API-herstart. Bestaande runs
en al ingeplande aanvragen veranderen niet.

Tokens: 512, 1024, 2048, 4096, 8192, 16384 of provider-default (`null` in de API,
`provider` in de environment). Provider-default laat `max_tokens` weg en betekent
geen onbeperkte output. Herstellen verwijdert de voorkeur en gebruikt opnieuw de
environment defaults; het verandert geen credentials of beveiligingsflags.

Het OpenRouter Chat Completions-endpoint krijgt `max_tokens` en
`reasoning: {effort: "low", exclude: true}`. Uitgeschakeld gebruikt
`reasoning: {enabled: false, exclude: true}` wanneer het model dit ondersteunt.
`exclude` voorkomt terugsturen van reasoningtekst; het schakelt reasoning niet uit.
Er wordt geen reasoningtekst opgeslagen of weergegeven.

De modelcatalogus bepaalt beschikbare efforts, temperature-ondersteuning en de
gerapporteerde maximale completionlengte. Onbevestigde of onondersteunde waarden
worden niet stilzwijgend genegeerd. De geconfigureerde Haiku 5.5 ondersteunt low,
medium, high en uitschakelen; de catalogus meldt geen temperature-ondersteuning.
Temperature blijft daarom null en wordt niet meegestuurd. Bij andere modellen
verschijnt de instelling alleen wanneer ondersteuning bevestigd is.

Bronnen: [modelcatalogus](https://openrouter.ai/api/v1/models) en
[OpenRouter reasoning-documentatie](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

## Responscontract en foutcategorieën

Naast de negen bestaande analysevelden bewaart iedere nieuwe poging diagnostiek:
HTTP-status, model, finish/native stop reason, input/output/reasoning/total tokens,
zichtbare inhoudslengte, geconfigureerd maximum, effort, requestduur en kosten waar
gerapporteerd. Ontbrekende metadata blijft onbekend. Outputtokens kunnen reasoning
bevatten; reasoning wordt niet nogmaals bij total tokens opgeteld.

| Code                                          | Betekenis                                               |
| --------------------------------------------- | ------------------------------------------------------- |
| `empty_content`                               | Geen zichtbare inhoud en geen reasoningtokens gemeld    |
| `reasoning_without_content`                   | Geen zichtbare inhoud; reasoningtokens wel gemeld       |
| `token_limit`                                 | Finish reason `length` of expliciete native tokenlimiet |
| `malformed_json`                              | Zichtbare inhoud is geen volledige geldige JSON         |
| `schema_validation_failed`                    | JSON voldoet niet aan het verwachte analyseschema       |
| `application_processing_error`                | Interne verwerkingsfout; geen SQL goedgekeurd           |
| `provider_error` / `network_or_timeout`       | Providerfout of onzekere netwerkuitkomst                |
| `provider_response_invalid` / `invalid_usage` | Onbruikbare envelope of metadata                        |
| `unsupported_settings`                        | Instelling niet ondersteund; geen generatie gestart     |

Een mislukte poging blijft FAILED, met outcome error, geen voorgestelde uitvoerbare
SQL en geen benchmark. De eerste maximaal 12000 tekens van eventueel zichtbare
gedeeltelijke inhoud worden geredigeerd bewaard voor inspectie. Credentials,
SQL-inhoud en reasoningtekst komen niet in diagnostieklogs terecht.

De UI toont de fout, usage en een link naar Settings. Opnieuw analyseren vraagt
een nieuwe kostenbevestiging; er is geen automatische betaalde herstelcall.
Een ongetest modeladvies wordt nooit een gevalideerde verbetering genoemd.

## API en kleine verbindingstest

- `GET /api/settings/ai`: instellingen, environment defaults en modelmogelijkheden.
- `PUT /api/settings/ai`: strict gevalideerde voorkeuren bewaren.
- `POST /api/settings/ai/reset`: environment defaults herstellen.
- `POST /api/settings/ai/test`: met `confirm_external_model: true` één vaste OK-prompt.

De nieuwe generatieverbindingstest is klein maar betaald: maximaal 512 tokens,
reasoning uit waar mogelijk, verwachte zichtbare tekst OK, geen SQL-context en geen
database. De bestaande `/api/system/check-model` blijft een kosteloze key/catalogus-
controle. Een HTTP 200 alleen geldt bij de nieuwe test niet als succes: zichtbare
inhoud, finish reason en het verwachte antwoord worden gecontroleerd.

## Werkelijke verificatie op 3 november 2026

- Echte verbindingstest: HTTP 200, `stop` / `end_turn`, 50 input, 4 output,
  0 reasoning, 54 totaal, 2 zichtbare tekens, 1.196 s, USD 0.000007 gerapporteerd.
- Eén echte C1-analyse van de kleine bestaande `revenue_orders`-fixture: compleet
  gestructureerd antwoord, HTTP 200, `stop` / `end_turn`, 1490 input, 1020 output,
  0 reasoning, 2510 totaal, 2296 zichtbare tekens, 7.411 s,
  USD 0.000659 gerapporteerd. Configuratie: 4096 / low.
- Correctheid en benchmark waren beide skipped: de SQL-veiligheidsflags bleven uit.
- Automatische tests vervangen providers en databases; ze controleren alle presets,
  het weglaten van max_tokens, efforts, ongeldige instellingen, persistentie na
  heropenen van de store, foutcategorieën, frontendbediening en ongewijzigde SQL-gates.
- De browserchecks voor Settings en de opgeslagen echte usage starten geen modelcall
  en wijzigen geen voorkeuren.

## Demonstreren

1. Open `/settings`: kies een ondersteund budget en effort en sla op.
2. Bevestig desgewenst de kleine betaalde test en klik Test AI connection.
3. Open een query en kies Analyze with AI of POC starten. Bevestig de modelcall.
4. Bekijk uitleg, rewrite of indexadvies, usage en de afzonderlijke validatiestatus.
5. Open dezelfde query opnieuw: opgeslagen analyses blijven direct zichtbaar.
6. Bij een fout: inspecteer de diagnostiek, pas Settings aan en vraag expliciet
   een nieuwe analyse aan. Een hogere limiet is geen garantie op volledige output.

# Voorbeelden uit de LLM-runs


## Goede voorbeelden (ACCEPTED)

### top_customers / C2_schema / herhaling 3  ->  ACCEPTED, speedup 211.16

Uitleg van het model: De originele query materialiseerde en aggregeerde de orders van alle tenants, en las die set twee keer (totalen en een DISTINCT ON-sort). In de herschrijving worden eerst de klanten van de tenant gefilterd en daarna gejoind met orders, met één aggregatie. `max(created_at)` geeft dezelfde waarde als de laatste order uit `DISTINCT ON`. Het filter op het laatste-orderdatumvenster staat in `HAVING`, zodat de semantiek gelijk blijft.

```sql
SELECT c.id,
       c.email,
       c.company,
       c.country_code,
       sum(o.total_cents) AS revenue,
       count(*)           AS order_count,
       max(o.created_at)  AS last_order_at
  FROM customers c
  JOIN orders o ON o.customer_id = c.id
 WHERE c.tenant_id = %(tenant_id)s
   AND o.status IN ('paid', 'processing', 'shipped', 'delivered')
 GROUP BY c.id
HAVING max(o.created_at) >= %(from)s
   AND max(o.created_at) <  %(to)s
 ORDER BY revenue DESC
 LIMIT %(limit)s
```

### top_customers / C3_plan / herhaling 1  ->  ACCEPTED, speedup 209.9

Uitleg van het model: De drie keer scannen van de gematerialiseerde CTE en de geneste lus met ~48 miljoen weggefilterde rijen zijn vervangen door één join en één aggregatie per klant. Omdat `last_order_at` gelijk is aan `max(created_at)` over dezelfde orders, volstaat een HAVING en is de `DISTINCT ON` niet meer nodig. Het tenantfilter op `customers` wordt nu vóór de aggregatie toegepast, en de kolommen, rijen en sortering blijven gelijk aan het origineel.

```sql
SELECT c.id,
       c.email,
       c.company,
       c.country_code,
       sum(o.total_cents) AS revenue,
       count(*)           AS order_count,
       max(o.created_at)  AS last_order_at
  FROM customers c
  JOIN orders o ON o.customer_id = c.id
 WHERE c.tenant_id = %(tenant_id)s
   AND o.status IN ('paid', 'processing', 'shipped', 'delivered')
 GROUP BY c.id
HAVING max(o.created_at) >= %(from)s
   AND max(o.created_at) <  %(to)s
 ORDER BY sum(o.total_cents) DESC
 LIMIT %(limit)s
```

### top_customers / C4_stats / herhaling 1  ->  ACCEPTED, speedup 206.43

Uitleg van het model: De query gebruikt nu één join en één aggregatie per klant. De laatste bestelling is `max(created_at)`, dus de `DISTINCT ON`-CTE en de gematerialiseerde CTE vervallen. Daarmee verdwijnt ook de geneste lus die 9799 keer een HashAggregate herhaalde (48 miljoen weggefilterde rijen). Het filter op tenant gebeurt vóór de aggregatie, en `c.id` is de primary key, dus de overige klantkolommen mogen zonder aggregatie in de SELECT staan.

```sql
SELECT c.id,
       c.email,
       c.company,
       c.country_code,
       sum(o.total_cents) AS revenue,
       count(*)           AS order_count,
       max(o.created_at)  AS last_order_at
  FROM customers c
  JOIN orders o ON o.customer_id = c.id
 WHERE c.tenant_id = %(tenant_id)s
   AND o.status IN ('paid', 'processing', 'shipped', 'delivered')
 GROUP BY c.id
HAVING max(o.created_at) >= %(from)s
   AND max(o.created_at) <  %(to)s
 ORDER BY revenue DESC
 LIMIT %(limit)s
```


## Foute voorbeelden (door het framework afgekeurd)

### revenue_orders / C2_schema / herhaling 3  ->  REJECTED_NOT_EQUIVALENT

Wat ging er mis: waarde in de query die in het origineel niet staat: 'delivery'. Details: big/full: ROWCOUNT_MISMATCH 23610 tegenover 11780 rijen; big/recent: ROWCOUNT_MISMATCH 5438 tegenover 2784 rijen; big/boundary: ROWCOUNT_MISMATCH 23609 tegenover 11780 rijen; small/full: ROWCOUNT_MISMATCH 13680 tegenover 6925 rijen; small/recent: ROWCOUNT_MISMATCH 3163 tegenover 1623 rijen; small/bo

Uitleg van het model: Een herschrijving levert hier geen winst op. Een index op `(tenant_id, created_at)` zou wel helpen, maar die mag ik niet voorstellen als wijziging in de query.

```sql
SELECT o.id,
       o.created_at,
       o.status,
       o.total_cents,
       o.currency
  FROM orders o
 WHERE o.tenant_id = %(tenant_id)s
   AND o.created_at >= %(from)s
   AND o.created_at <  %(to)s
   AND o.status IN ('paid', 'processing', 'shipped', 'delivery')
```

### revenue_orders / C3_plan / herhaling 1  ->  REJECTED_NOT_EQUIVALENT

Wat ging er mis: waarde in de query die in het origineel niet staat: 'delivery'. Details: big/full: ROWCOUNT_MISMATCH 23610 tegenover 11780 rijen; big/recent: ROWCOUNT_MISMATCH 5438 tegenover 2784 rijen; big/boundary: ROWCOUNT_MISMATCH 23609 tegenover 11780 rijen; small/full: ROWCOUNT_MISMATCH 13680 tegenover 6925 rijen; small/recent: ROWCOUNT_MISMATCH 3163 tegenover 1623 rijen; small/bo

Uitleg van het model: Ik heb de query inhoudelijk ongewijzigd gelaten. Hij is al een eenvoudige filterquery zonder joins of aggregaties en draait in ongeveer 9 ms. Een herschrijving levert geen winst op: de planner gebruikt al een bitmap scan op `tenant_id`, en een echte versnelling kan alleen via een betere index (bijvoorbeeld op `(tenant_id, created_at)`), en die mag ik hier niet voorstellen.

```sql
SELECT o.id,
       o.created_at,
       o.status,
       o.total_cents,
       o.currency
  FROM orders o
 WHERE o.tenant_id = %(tenant_id)s
   AND o.created_at >= %(from)s
   AND o.created_at <  %(to)s
   AND o.status IN ('paid', 'processing', 'shipped', 'delivery')
```

### top_products / C1_query / herhaling 1  ->  REJECTED_NOT_EQUIVALENT

Wat ging er mis: waarde in de query die in het origineel niet staat: 'delivery'. Details: big/full: VALUE_MISMATCH 1751 rijen verschillen; big/recent: ROWCOUNT_MISMATCH 1750 tegenover 1680 rijen; big/boundary: VALUE_MISMATCH 1751 rijen verschillen; small/full: VALUE_MISMATCH 1011 rijen verschillen; small/recent: ROWCOUNT_MISMATCH 1009 tegenover 980 rijen; small/boundary: VALUE_MISMATCH 1

Uitleg van het model: Ik zie geen herschrijving die gegarandeerd hetzelfde resultaat geeft en sneller is. Vooraggregeren per (order, variant) verandert het type van `sum()` (bigint wordt numeric), en `GROUP BY` inkorten naar alleen `p.id` vereist een primary key die ik niet kan verifiëren. De planner pusht de filters op `orders` al zelf naar beneden.

```sql
-- name: top_products
-- owner: merchandising
-- params: tenant_id, from, to, limit
-- Best sellers by units and revenue. Line items reference the variant by its
-- string id (integration feed), so it is cast when joining the catalog.
SELECT p.id,
       p.sku,
       p.name,
       p.brand,
       p.currency,
       count(DISTINCT o.id)        AS order_count,
       sum(ol.quantity)            AS quantity,
       sum(ol.line_total_cents)    AS revenue_cents,
       count(DISTINCT pv.id)       AS variant_count
  FROM order_lines ol
  JOIN orders o           ON o.id = ol.order_id
  JOIN product_variants pv ON pv.id = ol.variant_id::uuid
  JOIN products p         ON p.id = pv.product_id
 WHERE o.tenant_id = %(tenant_id)s
   AND o.created_at >= %(from)s
   AND o.created_at <  %(to)s
   AND o.status IN ('paid', 'processing', 'shipped', 'delivery')
 GROUP BY p.id, p.sku, p.name, p.brand, p.currency
 ORDER BY quantity DESC, revenue_cents DESC
 LIMIT %(limit)s
```


## Gelijkwaardig maar trager

### top_products / C3_plan / herhaling 2  ->  EQUIVALENT_NOT_FASTER, speedup 0.52

Uitleg van het model: De dure sort op (product, order) met schijf-spill voor de twee `count(DISTINCT …)` is vervangen door hash-aggregaties op een eenmalig berekende, kleine tussenset. Daarna wordt `products` pas gejoind op de al geaggregeerde rijen. Datatypes van de sommen (`bigint` voor quantity, `numeric` voor revenue) blijven gelijk aan het origineel.

```sql
WITH base AS MATERIALIZED (
    SELECT pv.product_id,
           o.id               AS order_id,
           pv.id              AS variant_id,
           ol.quantity,
           ol.line_total_cents
      FROM order_lines ol
      JOIN orders o            ON o.id = ol.order_id
      JOIN product_variants pv ON pv.id = ol.variant_id::uuid
     WHERE o.tenant_id = %(tenant_id)s
       AND o.created_at >= %(from)s
       AND o.created_at <  %(to)s
       AND o.status IN ('paid', 'processing', 'shipped', 'delivered')
),
per_order AS (
    SELECT product_id,
           count(*)               AS order_count,
           sum(q)::bigint         AS quantity,
           sum(r)                 AS revenue_cents
      FROM (
            SELECT product_id, order_id,
                   sum(quantity)         AS q,
                   sum(line_total_cents) AS r
              FROM base
             GROUP BY product_id, order_id
           ) x
     GROUP BY product_id
),
per_variant AS (
    SELECT product_id, count(*) AS variant_count
      FROM (SELECT DISTINCT product_id, variant_id FROM base) v
     GROUP BY product_id
)
SELECT p.id,
       p.sku,
       p.name,
       p.brand,
       p.currency,
       po.order_count,
       po.quantity,
       po.revenue_cents,
       pvc.variant_count
  FROM per_order po
  JOIN per_variant pvc ON pvc.product_id = po.product_id
  JOIN products p      ON p.id = po.product_id
 ORDER BY po.quantity DESC, po.revenue_cents DESC
 LIMIT %(limit)s
```

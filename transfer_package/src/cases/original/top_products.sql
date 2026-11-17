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
   AND o.status IN ('paid', 'processing', 'shipped', 'delivered')
 GROUP BY p.id, p.sku, p.name, p.brand, p.currency
 ORDER BY quantity DESC, revenue_cents DESC
 LIMIT %(limit)s

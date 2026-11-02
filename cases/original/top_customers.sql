-- name: top_customers
-- owner: sales
-- params: tenant_id, from, to, limit
-- Customers ranked by revenue, with their most recent order. Only customers
-- whose last order falls inside the window are listed; this is what the
-- account managers asked for ("who was active this quarter").
WITH customer_orders AS MATERIALIZED (
    SELECT o.customer_id,
           o.id,
           o.total_cents,
           o.created_at
      FROM orders o
     WHERE o.status IN ('paid', 'processing', 'shipped', 'delivered')
),
totals AS (
    SELECT customer_id,
           sum(total_cents) AS revenue,
           count(*)         AS order_count
      FROM customer_orders
     GROUP BY customer_id
),
last_order AS (
    SELECT DISTINCT ON (customer_id)
           customer_id,
           created_at AS last_order_at
      FROM customer_orders
     ORDER BY customer_id, created_at DESC
)
SELECT c.id,
       c.email,
       c.company,
       c.country_code,
       t.revenue,
       t.order_count,
       lo.last_order_at
  FROM customers c
  JOIN totals     t  ON t.customer_id  = c.id
  JOIN last_order lo ON lo.customer_id = c.id
 WHERE c.tenant_id = %(tenant_id)s
   AND lo.last_order_at >= %(from)s
   AND lo.last_order_at <  %(to)s
 ORDER BY t.revenue DESC
 LIMIT %(limit)s

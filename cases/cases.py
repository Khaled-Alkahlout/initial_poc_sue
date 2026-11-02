"""Casusset: 4 query's uit de repo van SUE (alleen SELECT-herschrijvingen; geen index- of schemawijziging).

Per casus: de originele query, de sorteersleutel, parametersets en kandidaten met een verwachting.
`expected` is MIJN redenering (grondwaarheid van de proef): 'equivalent' of 'not_equivalent'.
Het framework moet dit zelf vaststellen; een verschil tussen mijn label en de uitkomst is een bevinding.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from cases.classes.candidate import Candidate
from cases.classes.case import Case

HERE = Path(__file__).parent
ACTIVE = "('paid', 'processing', 'shipped', 'delivered')"


def original(name: str) -> str:
    """
    Read the SQL text of an original query.

    Parameters
    ----------
    name : str
        Name of the query, equal to the file name without extension in ``cases/original/``.

    Returns
    -------
    str
        SQL text of the original query.
    """
    return (HERE / "original" / f"{name}.sql").read_text()


def make_ctx(conn) -> dict:
    """
    Derive the parameter building blocks from the database itself: a big and a small tenant and four time windows.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection to the database that contains the seeded data.

    Returns
    -------
    dict
        Context with the keys "big" and "small" (tenant ids) and "windows", a mapping
        ``tenant_id -> {"full", "recent", "empty", "boundary" -> (from, to)}``.
    """
    big, small = (conn.execute(
        "SELECT tenant_id FROM orders GROUP BY 1 ORDER BY count(*) {} LIMIT 1".format(d)).fetchone()[0] for d in ("DESC", "ASC"))
    ctx = {"big": big, "small": small, "windows": {}}
    for label, t in (("big", big), ("small", small)):
        lo, hi = conn.execute("SELECT min(created_at), max(created_at) FROM orders WHERE tenant_id=%s", (t,)).fetchone()
        ctx["windows"][t] = {
            "full": (datetime(2000, 1, 1), datetime(2100, 1, 1)),
            "recent": (hi - timedelta(days=90), hi + timedelta(days=1)),
            "empty": (datetime(2100, 1, 1), datetime(2101, 1, 1)),
            # bovengrens precies op de laatste order: een '<=' in plaats van '<' valt alleen hier op
            "boundary": (lo, hi),
        }
    return ctx


def std_params(limit):
    """
    Build the standard parameter-set generator: both tenants times all four time windows.

    Parameters
    ----------
    limit : int
        Value of the "limit" parameter in every parameter set.

    Returns
    -------
    callable
        Function ``f(ctx)`` that returns a list of ``(label, params)`` pairs, e.g. ("big/recent", {...}).
    """
    def f(ctx):
        """
        Generate the labelled parameter sets for the equivalence check.

        Parameters
        ----------
        ctx : dict
            Context as returned by ``make_ctx``.

        Returns
        -------
        list of tuple
            Pairs ``(label, params)``; one per tenant and time window.
        """
        out = []
        for tlabel in ("big", "small"):
            t = ctx[tlabel]
            for wlabel, (a, b) in ctx["windows"][t].items():
                out.append((f"{tlabel}/{wlabel}", {"tenant_id": t, "from": a, "to": b, "limit": limit}))
        return out
    return f


def std_timing(limit):
    """
    Build the standard timing-parameter generator: big tenant, full time window.

    Parameters
    ----------
    limit : int
        Value of the "limit" parameter.

    Returns
    -------
    callable
        Function ``f(ctx)`` that returns one parameter dict.
    """
    def f(ctx):
        """
        Generate the parameter set used for the timing measurement.

        Parameters
        ----------
        ctx : dict
            Context as returned by ``make_ctx``.

        Returns
        -------
        dict
            Parameters for the big tenant over the full time window.
        """
        t = ctx["big"]
        a, b = ctx["windows"][t]["full"]
        return {"tenant_id": t, "from": a, "to": b, "limit": limit}
    return f


# ---------------------------------------------------------------- top_products
TP = original("top_products")
TP_CANDS = [
    Candidate("R1_orders_eerst_filteren", f"""
WITH o AS (
  SELECT id FROM orders
   WHERE tenant_id = %(tenant_id)s AND created_at >= %(from)s AND created_at < %(to)s
     AND status IN {ACTIVE})
SELECT p.id, p.sku, p.name, p.brand, p.currency,
       count(DISTINCT o.id) AS order_count, sum(ol.quantity) AS quantity,
       sum(ol.line_total_cents) AS revenue_cents, count(DISTINCT pv.id) AS variant_count
  FROM o
  JOIN order_lines ol ON ol.order_id = o.id
  JOIN product_variants pv ON pv.id = ol.variant_id::uuid
  JOIN products p ON p.id = pv.product_id
 GROUP BY p.id, p.sku, p.name, p.brand, p.currency
 ORDER BY quantity DESC, revenue_cents DESC
 LIMIT %(limit)s""", "equivalent", "-"),
    Candidate("M1_count_zonder_distinct", TP.replace("count(DISTINCT o.id)", "count(o.id)"), "not_equivalent", "aggregatie"),
    Candidate("M2_bovengrens_inclusief", TP.replace("o.created_at <  %(to)s", "o.created_at <= %(to)s"), "not_equivalent", "grenswaarde"),
    Candidate("M3_status_paid_vergeten", TP.replace("('paid', 'processing', 'shipped', 'delivered')", "('processing', 'shipped', 'delivered')"), "not_equivalent", "filter"),
    Candidate("M4_varianten_zonder_distinct", TP.replace("count(DISTINCT pv.id)", "count(pv.id)"), "not_equivalent", "aggregatie"),
    Candidate("M5_geen_tiebreak", TP.replace("ORDER BY quantity DESC, revenue_cents DESC", "ORDER BY quantity DESC"), "not_equivalent", "sortering"),
    Candidate("M6_voor_aggregatie_per_variant", f"""
WITH per_variant AS (
  SELECT pv.product_id, pv.id AS variant_id, count(DISTINCT o.id) AS oc,
         sum(ol.quantity) AS q, sum(ol.line_total_cents) AS rev
    FROM order_lines ol
    JOIN orders o ON o.id = ol.order_id
    JOIN product_variants pv ON pv.id = ol.variant_id::uuid
   WHERE o.tenant_id = %(tenant_id)s AND o.created_at >= %(from)s AND o.created_at < %(to)s
     AND o.status IN {ACTIVE}
   GROUP BY pv.product_id, pv.id)
SELECT p.id, p.sku, p.name, p.brand, p.currency,
       sum(v.oc) AS order_count, sum(v.q) AS quantity, sum(v.rev) AS revenue_cents, count(*) AS variant_count
  FROM per_variant v JOIN products p ON p.id = v.product_id
 GROUP BY p.id, p.sku, p.name, p.brand, p.currency
 ORDER BY quantity DESC, revenue_cents DESC
 LIMIT %(limit)s""", "not_equivalent", "aggregatie (dubbeltelling)"),
    # Nieuw: LEFT JOIN met de filters in de ON-clausule. De filters schrappen dan geen orderregels meer,
    # ze maken alleen o NULL: alle regels van alle tenants tellen mee in quantity/revenue (count(DISTINCT o.id) niet).
    Candidate("M7_left_join_filter_in_on", f"""
SELECT p.id, p.sku, p.name, p.brand, p.currency,
       count(DISTINCT o.id) AS order_count, sum(ol.quantity) AS quantity,
       sum(ol.line_total_cents) AS revenue_cents, count(DISTINCT pv.id) AS variant_count
  FROM order_lines ol
  LEFT JOIN orders o ON o.id = ol.order_id
                    AND o.tenant_id = %(tenant_id)s AND o.created_at >= %(from)s AND o.created_at < %(to)s
                    AND o.status IN {ACTIVE}
  JOIN product_variants pv ON pv.id = ol.variant_id::uuid
  JOIN products p ON p.id = pv.product_id
 GROUP BY p.id, p.sku, p.name, p.brand, p.currency
 ORDER BY quantity DESC, revenue_cents DESC
 LIMIT %(limit)s""", "not_equivalent", "join (LEFT JOIN, filter in ON)"),
    # Nieuw: groeperen per variant in plaats van per product (verkeerde granulariteit; variant_count wordt 1).
    Candidate("M8_groeperen_per_variant", TP.replace("GROUP BY p.id, p.sku, p.name, p.brand, p.currency",
                                                     "GROUP BY p.id, p.sku, p.name, p.brand, p.currency, pv.id"),
              "not_equivalent", "groepering (granulariteit)"),
]

# ---------------------------------------------------------------- top_customers
TC = original("top_customers")
TC_CANDS = [
    Candidate("R1_tenantfilter_in_cte", TC.replace("AS MATERIALIZED (", "AS (").replace(
        "     WHERE o.status IN ('paid', 'processing', 'shipped', 'delivered')",
        "     WHERE o.tenant_id = %(tenant_id)s\n       AND o.status IN ('paid', 'processing', 'shipped', 'delivered')"),
        "equivalent", "- (aanname: order en klant horen bij dezelfde tenant)"),
    Candidate("M1_omzet_alleen_in_venster", TC.replace(
        "     WHERE o.status IN ('paid', 'processing', 'shipped', 'delivered')",
        "     WHERE o.tenant_id = %(tenant_id)s AND o.created_at >= %(from)s AND o.created_at < %(to)s\n       AND o.status IN ('paid', 'processing', 'shipped', 'delivered')"
    ).replace("AS MATERIALIZED (", "AS ("), "not_equivalent", "semantiek (vensterbetekenis)"),
    Candidate("M2_eerste_in_plaats_van_laatste_order", TC.replace("ORDER BY customer_id, created_at DESC", "ORDER BY customer_id, created_at ASC"), "not_equivalent", "sortering/DISTINCT ON"),
    Candidate("M3_status_paid_vergeten", TC.replace("('paid', 'processing', 'shipped', 'delivered')", "('processing', 'shipped', 'delivered')"), "not_equivalent", "filter"),
    Candidate("M4_laatste_orderfilter_weg", TC.replace("   AND lo.last_order_at >= %(from)s\n   AND lo.last_order_at <  %(to)s\n", ""), "not_equivalent", "filter weggelaten"),
]

# ---------------------------------------------------------------- audit_log_page
AP = original("audit_log_page")


def audit_params(ctx):
    """
    Generate the parameter sets for audit_log_page: both tenants with and without a table filter, plus one offset.

    Parameters
    ----------
    ctx : dict
        Context as returned by ``make_ctx``.

    Returns
    -------
    list of tuple
        Pairs ``(label, params)``.
    """
    out = []
    for tlabel in ("big", "small"):
        t = ctx[tlabel]
        a, b = ctx["windows"][t]["full"]
        for tn in (None, "orders", "customers"):
            out.append((f"{tlabel}/table={tn}", {"tenant_id": t, "table_name": tn, "row_id": None,
                                                "from": a, "to": b, "limit": 200, "offset": 0}))
        out.append((f"{tlabel}/offset=50", {"tenant_id": t, "table_name": None, "row_id": None,
                                           "from": a, "to": b, "limit": 200, "offset": 50}))
    return out


def audit_timing(ctx):
    """
    Generate the parameter set used to time audit_log_page: big tenant, no table filter, first page.

    Parameters
    ----------
    ctx : dict
        Context as returned by ``make_ctx``.

    Returns
    -------
    dict
        Parameters for the timing measurement.
    """
    t = ctx["big"]
    a, b = ctx["windows"][t]["full"]
    return {"tenant_id": t, "table_name": None, "row_id": None, "from": a, "to": b, "limit": 200, "offset": 0}


AP_CANDS = [
    Candidate("R1_andere_opmaak", AP.replace("(%(table_name)s::text IS NULL OR a.table_name = %(table_name)s)", "(a.table_name = %(table_name)s OR %(table_name)s::text IS NULL)"), "equivalent", "-"),
    Candidate("M1_alleen_voor_null_filters", """
SELECT a.id, a.tenant_id, a.table_name, a.row_id, a.action, a.old_data, a.new_data, a.actor_id, a.is_system, a.created_at
  FROM audit_log a
 WHERE a.tenant_id = %(tenant_id)s AND a.created_at >= %(from)s AND a.created_at < %(to)s
 ORDER BY a.created_at DESC, a.id DESC
 LIMIT %(limit)s OFFSET %(offset)s""", "not_equivalent", "parameter-specifiek (filters genegeerd)"),
    Candidate("M2_offset_plus_een", AP.replace("OFFSET %(offset)s", "OFFSET %(offset)s + 1"), "not_equivalent", "paginering"),
    Candidate("M3_geen_id_tiebreak", AP.replace("ORDER BY a.created_at DESC, a.id DESC", "ORDER BY a.created_at DESC"), "not_equivalent", "sortering"),
    # Nieuw (performance-mutant): zelfde resultaat, maar een cast op de kolom maakt het predicaat niet-sargable,
    # zodat een index op tenant_id niet bruikbaar is. Verwacht: gelijkwaardig, niet sneller (speedup < 1).
    Candidate("P1_tenantfilter_als_tekst", AP.replace("WHERE a.tenant_id = %(tenant_id)s", "WHERE a.tenant_id::text = %(tenant_id)s::text"),
              "equivalent", "performance (niet-sargable predicaat)"),
]

# ---------------------------------------------------------------- revenue_orders (controle: geen verbetering nodig)
RO = original("revenue_orders")


def ro_params(ctx):
    """
    Generate the parameter sets for revenue_orders: the standard sets without the "limit" parameter.

    Parameters
    ----------
    ctx : dict
        Context as returned by ``make_ctx``.

    Returns
    -------
    list of tuple
        Pairs ``(label, params)``.
    """
    return [(l, {k: v for k, v in p.items() if k != "limit"}) for l, p in std_params(0)(ctx)]


def ro_timing(ctx):
    """
    Generate the parameter set used to time revenue_orders: the standard timing set without "limit".

    Parameters
    ----------
    ctx : dict
        Context as returned by ``make_ctx``.

    Returns
    -------
    dict
        Parameters for the timing measurement.
    """
    p = std_timing(0)(ctx)
    p.pop("limit")
    return p


RO_CANDS = [
    Candidate("R1_andere_opmaak", RO.replace("o.status IN ('paid', 'processing', 'shipped', 'delivered')", "o.status = ANY (ARRAY['paid','processing','shipped','delivered'])"), "equivalent", "-"),
    Candidate("M1_status_leveringen_weg", RO.replace("('paid', 'processing', 'shipped', 'delivered')", "('paid', 'processing', 'shipped')"), "not_equivalent", "filter"),
    Candidate("M2_bovengrens_inclusief", RO.replace("o.created_at <  %(to)s", "o.created_at <= %(to)s"), "not_equivalent", "grenswaarde"),
]


def tc_params(ctx):
    """
    Generate a reduced set of parameter sets for top_customers, because the original query is slow.

    Parameters
    ----------
    ctx : dict
        Context as returned by ``make_ctx``.

    Returns
    -------
    list of tuple
        Pairs ``(label, params)`` for four of the eight standard combinations.
    """
    keep = {"big/recent", "big/empty", "small/full", "small/boundary"}  # trage query: beperkte set
    return [(l, p) for l, p in std_params(100000)(ctx) if l in keep]


CASES = [
    Case("top_products", TP, ["quantity", "revenue_cents"], std_params(100000), std_timing(100000), TP_CANDS),
    Case("top_customers", TC, ["revenue"], tc_params, std_timing(100000), TC_CANDS),
    Case("audit_log_page", AP, ["created_at", "id"], audit_params, audit_timing, AP_CANDS),
    Case("revenue_orders", RO, None, ro_params, ro_timing, RO_CANDS),
]

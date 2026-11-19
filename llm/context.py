"""Cumulative PostgreSQL context without row data or plan predicates."""

import json

from cases.cases import make_ctx
from sqlglot import exp
from validator.checker import inspect_sql, read_snapshot, require_tables

CONDITIONS = ["C1_query", "C2_schema", "C3_plan", "C4_stats"]
MAX_CONTEXT_CHARS = 8000


def schema_text(conn, tables):
    out = []
    for table in sorted(tables):
        columns = conn.execute(
            """SELECT column_name, data_type, is_nullable
                 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position LIMIT 100""",
            (table,),
        ).fetchall()
        lines = [
            f"  {name} {kind}{'' if nullable == 'YES' else ' NOT NULL'}"
            for name, kind, nullable in columns
        ]
        out.append(f"TABLE public.{table} (\n" + ",\n".join(lines) + "\n)")
        indexes = conn.execute(
            """SELECT idx.relname, ix.indisunique, array(
                   SELECT att.attname FROM unnest(ix.indkey) WITH ORDINALITY AS k(num, ord)
                     JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = k.num
                    WHERE k.ord <= ix.indnkeyatts ORDER BY k.ord)
                 FROM pg_index ix
                 JOIN pg_class rel ON rel.oid = ix.indrelid
                 JOIN pg_class idx ON idx.oid = ix.indexrelid
                 JOIN pg_namespace ns ON ns.oid = rel.relnamespace
                WHERE ns.nspname = 'public' AND rel.relname = %s AND ix.indisvalid
                ORDER BY idx.relname LIMIT 50""",
            (table,),
        ).fetchall()
        for name, unique, keys in indexes:
            out.append(
                f"  {'UNIQUE ' if unique else ''}INDEX {name}: {', '.join(keys)}"
            )
    return "\n".join(out)


def plan_text(conn, sql, params):
    """Keep planner estimates and node structure. Never execute EXPLAIN ANALYZE."""
    (plan,) = conn.execute("EXPLAIN (FORMAT JSON) " + sql, params).fetchone()
    fields = (
        "Node Type",
        "Join Type",
        "Relation Name",
        "Index Name",
        "Startup Cost",
        "Total Cost",
        "Plan Rows",
        "Plan Width",
    )

    def summarize_node(node):
        safe = {field: node[field] for field in fields if field in node}
        if node.get("Plans"):
            safe["Plans"] = [summarize_node(child) for child in node["Plans"]]
        return safe

    return json.dumps(summarize_node(plan[0]["Plan"]), ensure_ascii=False)


def stats_text(conn, tables, columns):
    out = []
    for table in sorted(tables):
        rows, pages = conn.execute(
            """SELECT c.reltuples::bigint, c.relpages FROM pg_class c
                 JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = %s""",
            (table,),
        ).fetchone()
        out.append(f"public.{table}: geschat {rows} rijen, {pages} pagina's")
        for column, null_frac, distinct in conn.execute(
            """SELECT attname, null_frac, n_distinct FROM pg_stats
                WHERE schemaname = 'public' AND tablename = %s
                  AND attname::text = ANY(%s) ORDER BY attname LIMIT 100""",
            (table, sorted(columns)),
        ).fetchall():
            out.append(f"  {column}: null_frac={null_frac:.3f}, n_distinct={distinct}")
    return "\n".join(out)


def build_context(conn, case, ctx, condition: str, *, recent_order_limit=None) -> dict:
    """Adapt the package's C1–C4 context to approved, bounded metadata reads."""
    level = CONDITIONS.index(condition)
    query = inspect_sql(case.original)
    blocks = {"query": case.original.strip()}
    if level == 0:
        return blocks
    with read_snapshot(conn):
        needs_profile = level >= 2 and ctx is None
        require_tables(conn, query.tables | ({"orders"} if needs_profile else set()))
        blocks["schema"] = schema_text(conn, query.tables)
        if level >= 2:
            profile = (
                make_ctx(conn, recent_order_limit=recent_order_limit)
                if needs_profile
                else ctx
            )
            timing = case.timing_params(profile)
            if set(timing) != query.parameters:
                raise ValueError(
                    "Het parameterprofiel voor het queryplan is onvolledig."
                )
            blocks["plan"] = plan_text(conn, case.original, timing)
        if level >= 3:
            columns = {column.name for column in query.tree.find_all(exp.Column)}
            blocks["stats"] = stats_text(conn, query.tables, columns)
    return {
        name: value
        if name == "query" or len(value) <= MAX_CONTEXT_CHARS
        else value[:MAX_CONTEXT_CHARS] + "\n… (afgekapt)"
        for name, value in blocks.items()
    }

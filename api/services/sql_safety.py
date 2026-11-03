"""Additional execution admission for AI proposals; no equivalence claim."""

import re
import sqlglot
from sqlglot import exp
from validator.checker import static_check


def proposal_check(sql: str) -> tuple[bool, str]:
    ok, reason = static_check(sql)
    if not ok:
        return ok, reason
    root = sqlglot.parse_one(re.sub(r"%\(\w+\)s", "NULL", sql), read="postgres")
    if root.find(exp.Into, exp.Lock) or root.find(exp.Anonymous):
        return (
            False,
            "UNSAFE_OR_UNKNOWN_OPERATION: INTO, locks of onbekende functies zijn niet toegestaan voor automatische tests.",
        )
    return True, "Eén ondersteund SELECT; geen uitvoering of correctheidsbewijs."

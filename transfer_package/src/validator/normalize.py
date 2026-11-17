"""Maak resultaatwaarden vergelijkbaar, ongeacht Python-type (int/Decimal/float, datum, uuid, json)."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal


def norm_value(v):
    """
    Convert one result value to a comparable form, independent of its Python type.

    Numbers (int, float, Decimal) become the same string when they are numerically
    equal, dates and datetimes become ISO strings, dicts and lists become sorted JSON
    strings, and everything else is converted with ``str``.

    Parameters
    ----------
    v : object
        A single value from a result row.

    Returns
    -------
    None or bool or str
        None and booleans are returned unchanged; all other values as a prefixed string.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, Decimal)):
        # 5, 5.0 en Decimal('5.00') moeten gelijk zijn
        return "num:" + format(Decimal(str(v)).normalize(), "f")
    if isinstance(v, (datetime, date)):
        return "ts:" + v.isoformat()
    if isinstance(v, (dict, list)):
        return "json:" + json.dumps(v, sort_keys=True, default=str)
    return str(v)


def norm_row(row):
    """
    Normalise every value of a result row with :func:`norm_value`.

    Parameters
    ----------
    row : tuple
        One row of a query result.

    Returns
    -------
    tuple
        The row with all values normalised, ready for equality checks and counting.
    """
    return tuple(norm_value(v) for v in row)

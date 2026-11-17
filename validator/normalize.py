"""Hashable representations that retain value types and exact numeric equality."""

import math
from decimal import Decimal


def norm_value(value):
    if isinstance(value, dict):
        return dict, frozenset((key, norm_value(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return type(value), tuple(norm_value(item) for item in value)
    if isinstance(value, Decimal) and value.is_nan():
        return Decimal, "NaN"
    if isinstance(value, float) and math.isnan(value):
        return float, "NaN"
    if isinstance(value, memoryview):
        return bytes, value.tobytes()
    return type(value), value


def norm_row(row):
    return tuple(norm_value(value) for value in row)

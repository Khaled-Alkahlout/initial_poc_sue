"""Admission status exposed by the analysis workflow."""

from validator.checker import CheckedQuery, SqlRejected, check_rewrite, static_check


def proposal_check(sql: str, original: CheckedQuery | None = None) -> tuple[bool, str]:
    if original is None:
        return static_check(sql)
    try:
        check_rewrite(original, sql)
    except SqlRejected as exc:
        return False, str(exc)
    return True, "Eén toegestane SELECT met dezelfde parameterbindingen."

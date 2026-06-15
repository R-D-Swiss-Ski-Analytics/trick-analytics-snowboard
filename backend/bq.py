"""Thin BigQuery helper: shared client + parameterised query/insert."""
from functools import lru_cache
from typing import Any

from google.cloud import bigquery

from .config import BQ_LOCATION, GCP_PROJECT_ID


@lru_cache(maxsize=1)
def client() -> bigquery.Client:
    return bigquery.Client(project=GCP_PROJECT_ID, location=BQ_LOCATION)


def query_rows(sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Run a SELECT and return rows as dicts."""
    job_config = bigquery.QueryJobConfig()
    if params:
        job_config.query_parameters = [_to_param(k, v) for k, v in params.items()]
    rows = client().query(sql, job_config=job_config).result()
    return [dict(r.items()) for r in rows]


def execute(sql: str, params: dict[str, Any] | None = None) -> None:
    """Run a DML statement (INSERT/MERGE/DELETE/UPDATE)."""
    job_config = bigquery.QueryJobConfig()
    if params:
        job_config.query_parameters = [_to_param(k, v) for k, v in params.items()]
    client().query(sql, job_config=job_config).result()


def _to_param(name: str, value: Any) -> Any:
    if isinstance(value, bool):
        return bigquery.ScalarQueryParameter(name, "BOOL", value)
    if isinstance(value, int):
        return bigquery.ScalarQueryParameter(name, "INT64", value)
    if isinstance(value, float):
        return bigquery.ScalarQueryParameter(name, "FLOAT64", value)
    if isinstance(value, (list, tuple)):
        # array param: infer element type from the first non-null element (INT64 vs STRING).
        elems = list(value)
        if elems and all(isinstance(e, int) and not isinstance(e, bool) for e in elems):
            return bigquery.ArrayQueryParameter(name, "INT64", elems)
        return bigquery.ArrayQueryParameter(name, "STRING", [None if e is None else str(e) for e in elems])
    # default: STRING (date/timestamp serialise to ISO; BQ casts in SQL)
    return bigquery.ScalarQueryParameter(name, "STRING", None if value is None else str(value))

"""One-time migration: Supabase -> BigQuery `trick_collector`.

Maps the old name-keyed rows onto MSWSK athlete_ids (snowboard squad, field 236),
mints a UUID id per row, coerces types, and WRITE_TRUNCATE-loads each table.
Re-runnable. Prints a reconciliation report; rows whose `athlet` can't be matched
are still loaded (athlete_id = NULL) and listed, so nothing is silently dropped.

Usage:
    gcloud auth application-default login
    # SUPABASE_KEY defaults to the app's publishable key; override if needed.
    .venv/bin/python scripts/migrate_supabase_to_bq.py
"""
import json
import os
import sys
import unicodedata
import urllib.parse
import urllib.request
import uuid

from google.cloud import bigquery

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.tables import FLOAT_COLS, INT_COLS, TABLES  # noqa: E402

PROJECT = "swiss-ski-science-datahub"
DATASET = "trick_collector"
STAGING = f"{PROJECT}.myswissski_staging"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://oevjddfliqhtfvutllyf.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_38nueBUPcuSqwqK8QMI3VQ_rzohaNmh")

# Structural columns the migration owns, per table (besides the whitelisted ones).
STRUCT_COLS = ["id", "athlete_id", "athlet", "created_by", "created_at"]
HAS_UPDATED_AT = {"tricks", "standort"}

# Manual overrides where the Supabase display name doesn't auto-resolve.
NAME_OVERRIDES = {"lurawick": 835}  # active Lura Wick (ignore inactive 565)

bq = bigquery.Client(project=PROJECT)


def norm(s):
    if not s:
        return ""
    stripped = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return "".join(c for c in stripped.lower() if c.isalpha())


def build_name_to_id():
    rows = bq.query(f"""
        SELECT a.athlete_id, a.first_name, a.last_name
        FROM `{STAGING}.admin_athlete_extra_values_materialized` ev
        JOIN `{STAGING}.admin_athletes_materialized` a ON a.athlete_id = ev.athlete_id
        WHERE ev.field_id = 236 AND ev.field_value IN ('650','651')
    """).result()
    m = dict(NAME_OVERRIDES)
    for r in rows:
        name = " ".join(filter(None, [r["first_name"], r["last_name"]]))
        if name:
            m.setdefault(norm(name), int(r["athlete_id"]))
    return m


def supabase_rows(table):
    out, step = [], 1000
    for offset in range(0, 100000, step):
        url = f"{SUPABASE_URL}/rest/v1/{urllib.parse.quote(table)}?select=*&limit={step}&offset={offset}"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
        })
        with urllib.request.urlopen(req) as r:
            batch = json.loads(r.read().decode())
        out.extend(batch)
        if len(batch) < step:
            break
    return out


def coerce(col, v):
    if v is None or v == "":
        return None
    if col in FLOAT_COLS:
        try: return float(v)
        except (TypeError, ValueError): return None
    if col in INT_COLS:
        try: return int(float(v))
        except (TypeError, ValueError): return None
    if col == "datum":
        return str(v)[:10]  # YYYY-MM-DD
    return str(v)


def migrate():
    name_to_id = build_name_to_id()
    print(f"name->id map: {len(name_to_id)} snowboard athletes\n")
    unresolved = {}

    for table, cfg in TABLES.items():
        src = supabase_rows(table)
        cols = cfg["columns"]
        out = []
        for row in src:
            athlet = row.get("athlet")
            aid = name_to_id.get(norm(athlet)) if athlet else None
            if athlet and aid is None:
                unresolved.setdefault(table, {}).setdefault(athlet, 0)
                unresolved[table][athlet] += 1
            rec = {
                "id": str(uuid.uuid4()),
                "athlete_id": aid,
                "athlet": athlet,
                "created_by": "migration",
                "created_at": row.get("created_at") or row.get("datum") or "1970-01-01T00:00:00Z",
            }
            for c in cols:
                rec[c] = coerce(c, row.get(c))
            if table in HAS_UPDATED_AT:
                rec["updated_at"] = row.get("updated_at")
            out.append(rec)

        table_ref = f"{PROJECT}.{DATASET}.{table}"
        job = bq.load_table_from_json(
            out, table_ref,
            job_config=bigquery.LoadJobConfig(
                write_disposition="WRITE_TRUNCATE",
                schema=bq.get_table(table_ref).schema,  # use destination schema
            ),
        )
        job.result()
        print(f"{table:18s} supabase={len(src):5d}  loaded={len(out):5d}")

    if unresolved:
        print("\n⚠ unresolved athlete names (loaded with athlete_id = NULL):")
        for table, names in unresolved.items():
            for n, c in names.items():
                print(f"    {table}: {n!r} ({c} rows)")
    else:
        print("\n✓ every athlet resolved to an MSWSK athlete_id")


if __name__ == "__main__":
    migrate()

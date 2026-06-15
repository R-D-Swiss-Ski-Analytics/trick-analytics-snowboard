"""Backfill the `standort` (assessment) table from CSV exports.

Source: the two trick_analytics_assessment_*.csv exports (Aron Wagner + the
backup of the other four athletes). Columns already match `standort`. We map the
display name to the verified MSWSK athlete_id, mint a fresh UUID id, preserve the
original created_at/updated_at/status/coach_rating, and WRITE_TRUNCATE-load
(idempotent — re-running replaces the table, it doesn't duplicate).

Usage:
    .venv/bin/python scripts/backfill_standort_csv.py \
        ~/Downloads/trick_analytics_assessment_aron_wagner_snowboard.csv \
        ~/Downloads/trick_analytics_assessment_backup.csv
"""
import csv
import os
import sys
import unicodedata
import uuid

from google.cloud import bigquery

PROJECT = "swiss-ski-science-datahub"
TABLE = f"{PROJECT}.trick_collector.standort"

# Verified against admin_athletes_materialized (all Park & Pipe / snowboard freestyle).
NAME_TO_ID = {
    "aronwagner": 1478,
    "louannen": 1483,
    "timegger": 1484,
    "maxencepetzoldt": 1485,
    "jasonzacharopoulos": 1486,
}

# columns copied straight from the CSV into standort
STR_COLS = ["disziplin", "trick_label", "drehrichtung", "flips", "achse", "rotation",
            "absprung", "grab", "bringback", "railart", "slideform", "slidevar",
            "inspin", "swap", "outspin", "notiz", "status", "coach_kommentar", "coach_video"]

bq = bigquery.Client(project=PROJECT)


def norm(s):
    if not s:
        return ""
    st = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return "".join(c for c in st.lower() if c.isalpha())


def clean(v):
    return v if (v is not None and v != "") else None


def main(paths):
    rows, seen, unresolved = [], set(), {}
    for p in paths:
        with open(os.path.expanduser(p), newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                # de-dupe across files on (athlet, trick_label, datum)
                key = (r["athlet"], r["trick_label"], r["datum"])
                if key in seen:
                    continue
                seen.add(key)
                aid = NAME_TO_ID.get(norm(r["athlet"]))
                if aid is None:
                    unresolved[r["athlet"]] = unresolved.get(r["athlet"], 0) + 1
                rec = {
                    "id": str(uuid.uuid4()),
                    "athlete_id": aid,
                    "athlet": r["athlet"],
                    "datum": (r.get("datum") or "")[:10] or None,
                    "coach_rating": int(r["coach_rating"]) if (r.get("coach_rating") or "").strip().isdigit() else None,
                    "created_by": "backfill-csv",
                    "created_at": clean(r.get("created_at")) or "2026-01-01T00:00:00Z",
                    "updated_at": clean(r.get("updated_at")),
                }
                for c in STR_COLS:
                    rec[c] = clean(r.get(c))
                rows.append(rec)

    job = bq.load_table_from_json(
        rows, TABLE,
        job_config=bigquery.LoadJobConfig(
            write_disposition="WRITE_TRUNCATE",
            schema=bq.get_table(TABLE).schema,
        ),
    )
    job.result()

    # one audit row for the batch
    bq.query(
        f"INSERT INTO `{PROJECT}.trick_collector.audit_log` "
        "(event_id, event_type, user_id, payload, created_at) "
        "VALUES (@id, 'standort.backfill_csv', 'backfill', "
        "PARSE_JSON(TO_JSON_STRING(STRUCT(@n AS n_rows))), CURRENT_TIMESTAMP())",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("id", "STRING", str(uuid.uuid4())),
            bigquery.ScalarQueryParameter("n", "INT64", len(rows)),
        ]),
    ).result()

    print(f"loaded {len(rows)} rows into standort")
    if unresolved:
        print("⚠ unresolved (athlete_id NULL):", unresolved)
    else:
        print("✓ every athlet mapped to an MSWSK athlete_id")


if __name__ == "__main__":
    args = sys.argv[1:] or [
        "~/Downloads/trick_analytics_assessment_aron_wagner_snowboard.csv",
        "~/Downloads/trick_analytics_assessment_backup.csv",
    ]
    main(args)

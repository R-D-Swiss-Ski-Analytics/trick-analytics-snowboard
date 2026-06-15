# Trick Collector Snowboard

Coach/athlete tool for tracking Swiss-Ski snowboard-freestyle tricks, assessments
and progression. FastAPI backend + single-page frontend on Cloud Run, BigQuery
storage, MSWSK-driven signed-URL auth.

## Architecture

- **Backend** `backend/` — FastAPI. Serves `frontend/index.html` at `GET /` and a
  scoped CRUD API at `/api/*`. BigQuery via ADC (Cloud Run runtime SA).
- **Frontend** `frontend/index.html` — single-file vanilla-JS app. Talks to the
  backend through a tiny `fetch` shim (`db.from(...)`), no framework, no build.
- **Auth** — signed-URL token, no login form:
  `?id_coach=<id>_<md5("coach"+id+secret)>` / `?id_athlete=<id>_<md5("athlete"+id+secret)>`,
  secret = Secret Manager `md5-myswissski`. The role is folded into the hash so a
  coach link can't be replayed as an athlete link.
- **Scoping (squad model)** — snowboard-freestyle identity comes from the MSWSK
  custom field **236 "Sportart"** (650 / 651). Any tagged coach sees the whole
  snowboard squad; an athlete sees only themselves; anyone untagged → 403. The
  noisy `coaches_assigned_athletes_materialized` is deliberately **not** used.

## BigQuery (`swiss-ski-science-datahub`, `europe-west6`)

Dataset `trick_collector`: `tricks`, `standort`, `athlete_notebook`, `notebook`,
`trainerurteil`, `audit_log`. Every app row carries `athlete_id INT64` (MSWSK id,
the scoping key) + `athlet STRING` (display name). Squad membership + names are
read from `myswissski_staging` (`admin_athlete_extra_values_materialized`,
`admin_coach_extra_values_materialized`, `admin_athletes_materialized`,
`coaches_materialized`).

## Local development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
gcloud auth application-default login
.venv/bin/uvicorn backend.main:app --reload --port 8000
# mint a link (needs the secret):
SECRET=$(gcloud secrets versions access latest --secret=md5-myswissski --project=swiss-ski-science-datahub)
python scripts/mint_user_url.py --coach 717 http://localhost:8000
```

## Deploy

```bash
bash scripts/bootstrap_gcp.sh   # one-time: SA, IAM, dataset ACLs, Artifact Registry
bash scripts/deploy.sh          # build + deploy to Cloud Run (trick-collector)
```

One-time DB setup:
```bash
bq --location=europe-west6 mk -d swiss-ski-science-datahub:trick_collector
bq query --project_id=swiss-ski-science-datahub --use_legacy_sql=false < sql/create_tables.sql
.venv/bin/python scripts/migrate_supabase_to_bq.py   # migrate legacy Supabase data
```

## Mint access links

```bash
SECRET=$(gcloud secrets versions access latest --secret=md5-myswissski --project=swiss-ski-science-datahub)
python scripts/mint_user_url.py --coach   717 https://trick-collector-xxxxx.a.run.app   # Matthew Cox
python scripts/mint_user_url.py --athlete  473 https://trick-collector-xxxxx.a.run.app   # Alex Lotorto
```

Snowboard coach_ids today: 253, 254, 258, 585, 586, 647, 717, 838.

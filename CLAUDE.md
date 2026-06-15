# Trick Collector Snowboard

Project-level instructions. Inherits the Swiss-Ski dev standards from
`/Users/marcgurber/SwissSki/CLAUDE.md`; this file overrides where they conflict.

---

## What this is

Coach/athlete tool for Swiss-Ski **snowboard-freestyle** trick tracking,
assessments and progression. **Cloud Run data-pipeline-adjacent service** (FastAPI
+ single-page frontend), BigQuery storage, MSWSK signed-URL auth.

> History: this was a single-file Supabase static app. It was re-platformed onto
> GCP/BigQuery + Cloud Run with coach-scoped auth (squad model). The old Supabase
> backend, the shared coach password, and per-athlete PINs are gone.

## Layout

- `backend/` — FastAPI. `main.py` (generic scoped CRUD + `/api/me` + serves the
  frontend at `GET /`), `auth.py` (token verify), `scope.py` (squad sets),
  `tables.py` (per-table column whitelist = the input contract), `bq.py`,
  `config.py`. `bq.py`/`config.py`/`Dockerfile` are copied from
  `29_Racing_Suit_Manager` — keep them in sync conceptually.
- `frontend/index.html` — vanilla-JS single file. Data layer is a Supabase-shaped
  `fetch` shim (`db.from(table).select()/.insert()/.update()/.delete()`) → `/api/*`.
  No framework, no build step. Edit this one file.
- `sql/create_tables.sql`, `scripts/` (bootstrap, deploy, mint, migrate), `Dockerfile`,
  `cloudbuild.yaml`.

## Auth & scoping (the important part)

- **Token, no login form — MySwissSki/LD_TR scheme.**
  `?id_coach=<id>_<md5(id+coach_secret)>` / `?id_athlete=<id>_<md5(id+base_secret)>`.
  `coach_secret` ≠ `base_secret` (role separation: a coach link can't be replayed
  as an athlete link). Both live in Secret Manager **`trick-collector-md5`** (JSON
  `{coach_secret, base_secret}`), copied from `23_LD_TR_2.0/.streamlit/secrets.toml`
  — the values MySwissSki actually signs deep-links with, so portal links work
  unchanged. **NOT `md5-myswissski`** (that 64-char secret is a different key for a
  different token type, `id_user=`, used by Racing-Suit-Manager — unrelated here).
- **No access gate.** Any valid MySwissSki link is allowed in — coaches/athletes
  only ever receive a link if they should have one. We do **not** reject by squad
  membership.
- **Per-coach scoping = MSWSK assignment ∩ roster.** A coach sees only the athletes
  **assigned to them** in `coaches_assigned_athletes_materialized` (key on
  `coach_id`, `deleted_at IS NULL`), intersected with the snowboard **roster**
  (MSWSK field **236 "Sportart"** = 650/651) so freeski/alpine stay out of the
  picker. An athlete is always scoped to their own id. Implemented in
  `scope.coach_assigned_athlete_ids()`.
- **`coaches_assigned_athletes_materialized` IS clean per-coach** when keyed on
  `coach_id` (e.g. Matthew Cox 717 → 21 snowboard athletes). An earlier note called
  it noisy — that was a bad `coach_id`→athlete-table join; ignore that note.
- `coach_id` and `athlete_id` are **separate MSWSK namespaces** — never join
  `coach_id` against the athlete table (that was the bad join above).

## Data model

Dataset `swiss-ski-science-datahub.trick_collector`: `tricks`, `standort`,
`athlete_notebook`, `notebook`, `trainerurteil`, `audit_log`. Every row carries
`athlete_id INT64` (scoping key) + `athlet STRING` (display). `id` is a
server-minted UUID. The backend stamps `athlete_id`/`athlet` from the resolved
identity on every write; the client never sets the scoping key.

## Working rules

- BigQuery is the source of truth; squad membership/names come from
  `myswissski_staging` (the runtime SA has READER there). Confirm a column exists
  before adding it to a query/insert.
- New client-settable fields must be added to the whitelist in `backend/tables.py`
  or they're silently ignored on write (this whitelist is the validation).
- Every mutation goes through `mutate_with_audit` → `audit_log`. Keep it that way.
- Test locally with a **Python 3.12** venv (the code uses 3.10+ union syntax; the
  system anaconda 3.9 will fail to import). Mint a token and exercise the golden
  path + a cross-athlete denial before deploying.
- Deploy: `bootstrap_gcp.sh` once, then `deploy.sh`. Service `trick-collector`,
  runtime SA `trick-collector-sa`, `--allow-unauthenticated` (the token IS the auth).
- Holds named minors' performance data — keep auth scoping intact, don't add
  untrusted third-party `<script src>`, escape user strings before DOM insertion.

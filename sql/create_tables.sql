-- Trick Collector Snowboard — app dataset schema.
-- Run once:  bq query --project_id=swiss-ski-science-datahub --use_legacy_sql=false < sql/create_tables.sql
-- (create the dataset first: bq --location=europe-west6 mk -d swiss-ski-science-datahub:trick_collector)
--
-- Athlete key: every table carries athlete_id INT64 (MSWSK id — the scoping key)
-- AND athlet STRING (display name) so the name-based frontend keeps working.
-- id is a server-minted STRING UUID.

CREATE TABLE IF NOT EXISTS `swiss-ski-science-datahub.trick_collector.tricks` (
  id           STRING NOT NULL,
  athlete_id   INT64,
  athlet       STRING,
  datum        DATE,
  typ          STRING,
  disziplin    STRING,            -- Jump | Rail | Halfpipe
  drehrichtung STRING, flips STRING, achse STRING, rotation STRING,
  absprung     STRING, grab STRING, bringback STRING, style STRING,
  railart      STRING, slideform STRING, slidevar STRING,
  inspin       STRING, swap STRING, outspin STRING,
  setup        FLOAT64, ausfuehrung FLOAT64, landung FLOAT64, gesamt FLOAT64,
  kommentar    STRING, trickaufbau STRING, videolink STRING, gelandet STRING,
  created_by   STRING,
  created_at   TIMESTAMP NOT NULL,
  updated_at   TIMESTAMP
)
PARTITION BY datum
CLUSTER BY athlete_id;

CREATE TABLE IF NOT EXISTS `swiss-ski-science-datahub.trick_collector.standort` (
  id           STRING NOT NULL,
  athlete_id   INT64,
  athlet       STRING,
  datum        DATE,
  disziplin    STRING,
  trick_label  STRING,
  drehrichtung STRING, flips STRING, achse STRING, rotation STRING,
  absprung     STRING, grab STRING, bringback STRING,
  railart      STRING, slideform STRING, slidevar STRING,
  inspin       STRING, swap STRING, outspin STRING,
  notiz        STRING,
  status       STRING,            -- erreicht | working-on
  coach_rating INT64,
  coach_kommentar STRING,
  coach_video  STRING,
  created_by   STRING,
  created_at   TIMESTAMP NOT NULL,
  updated_at   TIMESTAMP
)
CLUSTER BY athlete_id;

CREATE TABLE IF NOT EXISTS `swiss-ski-science-datahub.trick_collector.athlete_notebook` (
  id         STRING NOT NULL,
  athlete_id INT64,
  athlet     STRING,
  kat        STRING,
  datum      DATE,
  kommentar  STRING,
  created_by STRING,
  created_at TIMESTAMP NOT NULL
)
CLUSTER BY athlete_id;

CREATE TABLE IF NOT EXISTS `swiss-ski-science-datahub.trick_collector.notebook` (
  id         STRING NOT NULL,
  athlete_id INT64,
  athlet     STRING,
  coach      STRING,            -- free-text coach name (kept as-is from the old UI)
  kat        STRING,
  datum      DATE,
  kommentar  STRING,
  created_by STRING,
  created_at TIMESTAMP NOT NULL
)
CLUSTER BY athlete_id;

CREATE TABLE IF NOT EXISTS `swiss-ski-science-datahub.trick_collector.trainerurteil` (
  id         STRING NOT NULL,
  athlete_id INT64,
  athlet     STRING,
  coach      STRING,
  datum      DATE,
  lernkurve  FLOAT64, rail FLOAT64, kicker FLOAT64,
  halfpipe   FLOAT64, mental FLOAT64,
  notiz      STRING,
  created_by STRING,
  created_at TIMESTAMP NOT NULL
)
CLUSTER BY athlete_id;

CREATE TABLE IF NOT EXISTS `swiss-ski-science-datahub.trick_collector.audit_log` (
  event_id   STRING NOT NULL,
  event_type STRING NOT NULL,
  user_id    STRING,
  payload    JSON,
  created_at TIMESTAMP NOT NULL
);

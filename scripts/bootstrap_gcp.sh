#!/usr/bin/env bash
# One-time bootstrap: service account, IAM, secret access. Idempotent.
#
# Usage:
#   bash scripts/bootstrap_gcp.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-swiss-ski-science-datahub}"
REGION="${REGION:-europe-west6}"
SA_NAME="trick-collector-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
DATASET="trick_collector"
MD5_SECRET="md5-myswissski"

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

echo "==> Project: $PROJECT_ID  (number $PROJECT_NUMBER)"
echo "==> Runtime SA: $SA_EMAIL"

# 1. Required APIs
echo "==> Enabling APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com bigquery.googleapis.com \
    secretmanager.googleapis.com \
    --project="$PROJECT_ID"

# 2. Service account
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "==> Creating runtime SA"
    gcloud iam service-accounts create "$SA_NAME" \
        --display-name="Trick Collector Snowboard runtime" \
        --project="$PROJECT_ID"
else
    echo "==> Runtime SA already exists"
fi

# 3. BigQuery: WRITER on the app dataset (grant via dataset ACL, not project-wide)
echo "==> Granting WRITER on dataset $DATASET"
TMP_ACL=$(mktemp)
bq show --project_id="$PROJECT_ID" --format=prettyjson "${PROJECT_ID}:${DATASET}" > "$TMP_ACL"
python3 - <<PY > "${TMP_ACL}.new"
import json
d = json.load(open("${TMP_ACL}"))
acl = d.get("access", [])
if not any(a.get("role") == "WRITER" and a.get("userByEmail") == "${SA_EMAIL}" for a in acl):
    acl.append({"role": "WRITER", "userByEmail": "${SA_EMAIL}"})
d["access"] = acl
print(json.dumps(d, indent=2))
PY
bq update --project_id="$PROJECT_ID" --source="${TMP_ACL}.new" "${PROJECT_ID}:${DATASET}"
rm -f "$TMP_ACL" "${TMP_ACL}.new"

# 3b. BigQuery: project-level jobUser (needed to RUN queries)
echo "==> Granting bigquery.jobUser at project level"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/bigquery.jobUser" --condition=None >/dev/null

# 3c. Cross-dataset READER on myswissski_staging (squad scoping reads:
#     admin_athlete_extra_values_materialized, admin_coach_extra_values_materialized,
#     admin_athletes_materialized, coaches_materialized — all live here).
echo "==> Granting READER on myswissski_staging"
TMP_ACL=$(mktemp)
bq show --project_id="$PROJECT_ID" --format=prettyjson "${PROJECT_ID}:myswissski_staging" > "$TMP_ACL"
python3 - <<PY > "${TMP_ACL}.new"
import json
d = json.load(open("${TMP_ACL}"))
acl = d.get("access", [])
if not any(a.get("role") == "READER" and a.get("userByEmail") == "${SA_EMAIL}" for a in acl):
    acl.append({"role": "READER", "userByEmail": "${SA_EMAIL}"})
d["access"] = acl
print(json.dumps(d, indent=2))
PY
bq update --project_id="$PROJECT_ID" --source="${TMP_ACL}.new" "${PROJECT_ID}:myswissski_staging" >/dev/null
rm -f "$TMP_ACL" "${TMP_ACL}.new"

# 4. Secret access on md5-myswissski (least privilege, single secret)
echo "==> Granting secretAccessor on $MD5_SECRET"
gcloud secrets add-iam-policy-binding "$MD5_SECRET" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID" --condition=None >/dev/null

# 5. Cloud Build SA needs to deploy Cloud Run + actAs the runtime SA
echo "==> Granting Cloud Build run.admin + iam.serviceAccountUser"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${CB_SA}" \
    --role="roles/run.admin" --condition=None >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --member="serviceAccount:${CB_SA}" \
    --role="roles/iam.serviceAccountUser" \
    --project="$PROJECT_ID" --condition=None >/dev/null

# 6. Artifact Registry repo (reuse existing 'dataflow' repo if it exists)
if ! gcloud artifacts repositories describe dataflow --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "==> Creating Artifact Registry 'dataflow'"
    gcloud artifacts repositories create dataflow \
        --repository-format=docker --location="$REGION" --project="$PROJECT_ID"
else
    echo "==> Artifact Registry 'dataflow' already exists"
fi

echo
echo "Bootstrap complete. Next: bash scripts/deploy.sh"

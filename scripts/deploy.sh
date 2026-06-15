#!/usr/bin/env bash
# Submit a build + deploy to Cloud Run. Run from repo root.
set -euo pipefail
PROJECT_ID="${PROJECT_ID:-swiss-ski-science-datahub}"
gcloud builds submit --config cloudbuild.yaml --project="$PROJECT_ID" .
echo
echo "Service URL:"
gcloud run services describe trick-collector \
    --region=europe-west6 --project="$PROJECT_ID" \
    --format='value(status.url)'

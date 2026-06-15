"""Mint a personalised access URL (MySwissSki / LD_TR scheme).

coach links are signed with `coach_secret`, athlete links with `base_secret`
(read from Secret Manager `trick-collector-md5`, a JSON {coach_secret,
base_secret}). This matches what MySwissSki issues, so minted links are
interchangeable with portal deep-links.

Usage (uses ADC to read the secret — no need to paste it):
    python scripts/mint_user_url.py --coach   717 https://trick-collector-xxxxx.a.run.app
    python scripts/mint_user_url.py --athlete  473 https://trick-collector-xxxxx.a.run.app
"""
import argparse
import hashlib
import json
import sys

from google.cloud import secretmanager

PROJECT = "swiss-ski-science-datahub"
SECRET_NAME = "trick-collector-md5"


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--coach", type=int, metavar="COACH_ID")
    g.add_argument("--athlete", type=int, metavar="ATHLETE_ID")
    p.add_argument("service_url")
    args = p.parse_args()

    sm = secretmanager.SecretManagerServiceClient()
    raw = sm.access_secret_version(
        name=f"projects/{PROJECT}/secrets/{SECRET_NAME}/versions/latest"
    ).payload.data.decode().strip()
    secrets = json.loads(raw)

    if args.coach is not None:
        ident_id, key, param = args.coach, secrets["coach_secret"], "id_coach"
    else:
        ident_id, key, param = args.athlete, secrets["base_secret"], "id_athlete"

    h = hashlib.md5((str(ident_id) + key).encode()).hexdigest()
    print(f"{args.service_url.rstrip('/')}/?{param}={ident_id}_{h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Signed-URL token auth — MySwissSki scheme (same as 23_LD_TR_2.0).

The app is reached via a personalised MySwissSki deep-link, no login form:
  * coach:   ?id_coach=<coach_id>_<md5(coach_id + coach_secret)>
  * athlete: ?id_athlete=<athlete_id>_<md5(athlete_id + base_secret)>

MySwissSki signs coach links with `coach_secret` and athlete links with a
separate `base_secret` (see LD_TR `helpers/auth.py`). Using two distinct secrets
gives role separation: a coach link can't be replayed as an athlete link or
vice-versa. We validate against the SAME two secrets (Secret Manager
`trick-collector-md5`, a JSON {coach_secret, base_secret}), so MySwissSki-minted
links work unchanged.

`coach_id` and `athlete_id` are DIFFERENT MSWSK namespaces — the same integer is
a different person on each side. The role decides which set/dim table applies.
"""
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from functools import lru_cache

from fastapi import HTTPException, Query, Request
from google.cloud import secretmanager

from .config import GCP_PROJECT_ID, MD5_SECRET_NAME

log = logging.getLogger(__name__)


@dataclass
class Identity:
    role: str   # "coach" | "athlete"
    id: int     # MSWSK coach_id or athlete_id (namespace depends on role)


@lru_cache(maxsize=1)
def _secrets() -> dict:
    sm = secretmanager.SecretManagerServiceClient()
    name = f"projects/{GCP_PROJECT_ID}/secrets/{MD5_SECRET_NAME}/versions/latest"
    raw = sm.access_secret_version(name=name).payload.data.decode().strip()
    d = json.loads(raw)
    return {"coach_secret": d["coach_secret"], "base_secret": d["base_secret"]}


def decrypt_id(encoded_id: str, secret_key: str) -> int | None:
    """Validate `<id>_<md5(id+secret_key)>` (MySwissSki/LD_TR scheme); return int id."""
    if not encoded_id or "_" not in encoded_id:
        return None
    id_value, given_hash = encoded_id.rsplit("_", 1)
    if not id_value.isdigit():
        return None
    expected = hashlib.md5((id_value + secret_key).encode()).hexdigest()
    return int(id_value) if hmac.compare_digest(expected, given_hash) else None


async def require_identity(
    request: Request,
    id_coach: str | None = Query(default=None),
    id_athlete: str | None = Query(default=None),
) -> Identity:
    """FastAPI dependency. Resolves ?id_coach= (coach_secret) or ?id_athlete=
    (base_secret) to a verified Identity. 403 if neither validates.

    Snowboard-squad membership is enforced in scope.py, not here."""
    s = _secrets()
    if id_coach:
        cid = decrypt_id(id_coach, s["coach_secret"])
        if cid is None:
            log.warning("coach auth failed")
            raise HTTPException(403, "invalid auth token")
        ident = Identity("coach", cid)
    elif id_athlete:
        aid = decrypt_id(id_athlete, s["base_secret"])
        if aid is None:
            log.warning("athlete auth failed")
            raise HTTPException(403, "invalid auth token")
        ident = Identity("athlete", aid)
    else:
        raise HTTPException(403, "missing auth token")
    request.state.identity = ident
    return ident

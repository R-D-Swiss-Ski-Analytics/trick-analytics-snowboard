"""Snowboard-freestyle roster scoping.

Snowboard freestyle has no own MSWSK sport_id — it shares Park & Pipe (sport_id=1)
with Freeski. The discriminator is the custom field "Sportart" (field_id=236),
value 650 "Snowboard Freestyle" / 651 "Freeski & Snowboard Freestyle".

We do NOT gate access on squad membership: any valid MySwissSki link (auth.py)
is allowed in. Two things bound what a caller sees:
  * ROSTER (field 236 "Sportart" = Snowboard Freestyle): the universe of snowboard
    athletes, used to keep freeski/alpine out of the picker.
  * ASSIGNMENT (coaches_assigned_athletes_materialized): a COACH sees only the
    athletes assigned to them in MSWSK, intersected with the roster. An athlete is
    always scoped to their own id.
(coaches_assigned is clean per-coach once you key on coach_id with deleted_at IS
NULL — the earlier "noise" was a bad coach_id→athlete-table join.)
"""
import time
import unicodedata
from threading import Lock

from fastapi import HTTPException

from . import bq
from .auth import Identity
from .config import SNOWBOARD_OPTION_IDS, SPORTART_FIELD_ID

_STAGING = "swiss-ski-science-datahub.myswissski_staging"
_TTL_SECONDS = 1800  # 30 min — squad membership changes rarely
_cache: dict[str, tuple[float, object]] = {}
_lock = Lock()


def _cached(key: str, loader):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _TTL_SECONDS:
            return hit[1]
    value = loader()
    with _lock:
        _cache[key] = (now, value)
    return value


def _norm(s: str) -> str:
    """Lowercase, strip diacritics + non-letters: 'Lötscher' -> 'lotscher'."""
    if not s:
        return ""
    stripped = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return "".join(c for c in stripped.lower() if c.isalpha())


def snowboard_athlete_ids() -> set[int]:
    """The roster: athletes tagged Snowboard Freestyle (field 236)."""
    def load() -> set[int]:
        rows = bq.query_rows(
            f"SELECT DISTINCT athlete_id FROM `{_STAGING}.admin_athlete_extra_values_materialized` "
            f"WHERE field_id = @fid AND field_value IN UNNEST(@opts) AND athlete_id IS NOT NULL",
            {"fid": SPORTART_FIELD_ID, "opts": SNOWBOARD_OPTION_IDS},
        )
        return {int(r["athlete_id"]) for r in rows}
    return _cached("ath_ids", load)


def coach_assigned_athlete_ids(coach_id: int) -> set[int]:
    """Athletes assigned to this coach in MSWSK (coaches_assigned_athletes,
    deleted_at IS NULL), intersected with the snowboard roster so the picker stays
    snowboard-only (some coaches are also assigned athletes from other sports)."""
    def load() -> set[int]:
        rows = bq.query_rows(
            f"SELECT DISTINCT athlete_id FROM `{_STAGING}.coaches_assigned_athletes_materialized` "
            f"WHERE coach_id = @cid AND deleted_at IS NULL AND athlete_id IS NOT NULL",
            {"cid": coach_id},
        )
        return {int(r["athlete_id"]) for r in rows} & snowboard_athlete_ids()
    return _cached(f"assigned:{coach_id}", load)


def athlete_names() -> dict[int, str]:
    """{athlete_id: 'First Last'} for the snowboard roster (MSWSK canonical names)."""
    def load() -> dict[int, str]:
        ids = sorted(snowboard_athlete_ids())
        if not ids:
            return {}
        rows = bq.query_rows(
            f"SELECT athlete_id, first_name, last_name "
            f"FROM `{_STAGING}.admin_athletes_materialized` "
            f"WHERE athlete_id IN UNNEST(@ids)",
            {"ids": ids},
        )
        out: dict[int, str] = {}
        for r in rows:
            name = " ".join(filter(None, [r.get("first_name"), r.get("last_name")]))
            if name:
                out[int(r["athlete_id"])] = name
        return out
    return _cached("ath_names", load)


def coach_name(coach_id: int) -> str:
    rows = bq.query_rows(
        f"SELECT first_name, last_name FROM `{_STAGING}.coaches_materialized` "
        f"WHERE coach_id = @cid LIMIT 1",
        {"cid": coach_id},
    )
    if rows:
        return " ".join(filter(None, [rows[0].get("first_name"), rows[0].get("last_name")])) or str(coach_id)
    return str(coach_id)


def name_to_id() -> dict[str, int]:
    """Normalised display-name -> athlete_id, for stamping athlete_id on writes."""
    return {_norm(name): aid for aid, name in athlete_names().items()}


def allowed_athlete_ids(identity: Identity) -> list[int]:
    """The athlete_ids this caller may read/write: their MSWSK-assigned snowboard
    athletes for a coach, just themselves for an athlete."""
    if identity.role == "coach":
        return sorted(coach_assigned_athlete_ids(identity.id))
    return [identity.id]


def resolve_target_id(identity: Identity, athlet_name: str | None) -> int:
    """For a write: which athlete_id the row belongs to, with scope enforcement.

    Athlete role -> always self. Coach role -> the named athlete (must be assigned)."""
    if identity.role == "athlete":
        return identity.id
    if not athlet_name:
        raise HTTPException(400, "athlet (name) required")
    aid = name_to_id().get(_norm(athlet_name))
    if aid is None or aid not in coach_assigned_athlete_ids(identity.id):
        raise HTTPException(403, f"athlete '{athlet_name}' not assigned to you")
    return aid


def assert_can_access_id(identity: Identity, athlete_id: int | None) -> None:
    """For update/delete by row id: the row's athlete_id must be in the caller's scope."""
    if athlete_id is None:
        raise HTTPException(404, "row not found")
    if identity.role == "athlete" and athlete_id != identity.id:
        raise HTTPException(403, "forbidden")
    if identity.role == "coach" and athlete_id not in coach_assigned_athlete_ids(identity.id):
        raise HTTPException(403, "forbidden")

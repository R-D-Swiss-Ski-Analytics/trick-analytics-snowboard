"""FastAPI app for Trick Collector Snowboard.

Single Cloud Run service:
  - GET    /api/me                  identity + the squad's athlete list
  - {GET,POST,PATCH,DELETE} /api/{table}[/{id}]   scoped CRUD on the 5 app tables
  - GET    /api/healthz             liveness (no auth)
  - GET    /                        serves frontend/index.html

Auth = role-salted md5 token (auth.py). Scoping = snowboard squad model (scope.py).
"""
import json
import logging
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse

from . import bq, scope
from .auth import Identity, require_identity
from .config import fq
from .tables import FLOAT_COLS, INT_COLS, TABLES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("trick-collector")

app = FastAPI(title="Trick Collector Snowboard API", version="1.0")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# ---------------------------------------------------------------------------
# Mutation + audit (single BQ script; audit row always written alongside the DML).
# ---------------------------------------------------------------------------
def mutate_with_audit(mutation_sql: str, params: dict, event_type: str,
                      user_id: str, payload: dict) -> None:
    script = (
        f"{mutation_sql};\n"
        f"INSERT INTO {fq('audit_log')} (event_id, event_type, user_id, payload, created_at) "
        "VALUES (@_aid, @_atype, @_auser, PARSE_JSON(@_apayload), CURRENT_TIMESTAMP());"
    )
    bq.execute(script, {
        **params,
        "_aid": str(uuid.uuid4()),
        "_atype": event_type,
        "_auser": user_id,
        "_apayload": json.dumps(payload, default=str),
    })


def _coerce(col: str, value):
    """Bind-type coercion so FLOAT64/INT64 columns don't get a mistyped param."""
    if value is None or value == "":
        return None
    if col in FLOAT_COLS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if col in INT_COLS:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    return str(value)


def _table_cfg(table: str) -> dict:
    cfg = TABLES.get(table)
    if cfg is None:
        raise HTTPException(404, "unknown table")
    return cfg


def _guard_table(identity: Identity, cfg: dict) -> None:
    if cfg["coach_only"] and identity.role != "coach":
        raise HTTPException(403, "coach-only resource")


def _col_expr(col: str) -> str:
    """SQL expression for a column's bind param (DATE() wraps the date columns)."""
    return f"DATE(@{col})" if col == "datum" else f"@{col}"


# ---------------------------------------------------------------------------
# health + identity
# ---------------------------------------------------------------------------
@app.get("/api/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/me")
def me(identity: Identity = Depends(require_identity)):
    names = scope.athlete_names()
    if identity.role == "coach":
        allowed = scope.allowed_athlete_ids(identity)  # MSWSK-assigned ∩ snowboard roster
        athletes = [{"athlete_id": aid, "name": names.get(aid, str(aid))}
                    for aid in sorted(allowed, key=lambda a: names.get(a, ""))]
        return {"role": "coach", "id": identity.id,
                "name": scope.coach_name(identity.id), "athletes": athletes}
    # athlete: only themselves
    self_name = names.get(identity.id, str(identity.id))
    return {"role": "athlete", "id": identity.id, "name": self_name,
            "athletes": [{"athlete_id": identity.id, "name": self_name}]}


# ---------------------------------------------------------------------------
# generic scoped CRUD
# ---------------------------------------------------------------------------
@app.get("/api/{table}")
def list_rows(table: str, identity: Identity = Depends(require_identity),
              athlet: str | None = Query(default=None),
              limit: int | None = Query(default=None)):
    cfg = _table_cfg(table)
    _guard_table(identity, cfg)

    ids = scope.allowed_athlete_ids(identity)
    if not ids:
        return []
    params: dict = {"ids": ids}
    where = "athlete_id IN UNNEST(@ids)"
    if athlet:  # optional filter WITHIN the allowed set (never a trust boundary)
        where += " AND athlet = @athlet"
        params["athlet"] = athlet
    sql = f"SELECT * FROM {fq(table)} WHERE {where} ORDER BY {cfg['order_by']}"
    if limit and 0 < limit <= 1000:
        sql += f" LIMIT {int(limit)}"
    return bq.query_rows(sql, params)


@app.post("/api/{table}", status_code=201)
async def create_row(table: str, request: Request,
                     identity: Identity = Depends(require_identity)):
    cfg = _table_cfg(table)
    _guard_table(identity, cfg)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be an object")

    target_id = scope.resolve_target_id(identity, body.get("athlet"))
    athlet_name = scope.athlete_names().get(target_id, body.get("athlet"))

    set_cols = [c for c in cfg["columns"] if c in body]
    row_id = str(uuid.uuid4())
    cols = ["id", "athlete_id", "athlet", *set_cols, "created_by", "created_at"]
    vals = ["@id", "@athlete_id", "@athlet",
            *[_col_expr(c) for c in set_cols], "@created_by", "CURRENT_TIMESTAMP()"]
    params: dict = {
        "id": row_id, "athlete_id": target_id, "athlet": athlet_name,
        "created_by": f"{identity.role}:{identity.id}",
        **{c: _coerce(c, body[c]) for c in set_cols},
    }
    sql = f"INSERT INTO {fq(table)} ({', '.join(cols)}) VALUES ({', '.join(vals)})"
    mutate_with_audit(sql, params, f"{table}.create", params["created_by"], body)
    return {"id": row_id, "athlete_id": target_id, "athlet": athlet_name}


@app.patch("/api/{table}/{row_id}")
async def update_row(table: str, row_id: str, request: Request,
                     identity: Identity = Depends(require_identity)):
    cfg = _table_cfg(table)
    _guard_table(identity, cfg)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be an object")

    owner = bq.query_rows(f"SELECT athlete_id FROM {fq(table)} WHERE id = @id LIMIT 1", {"id": row_id})
    if not owner:
        raise HTTPException(404, "row not found")
    scope.assert_can_access_id(identity, owner[0]["athlete_id"])

    set_cols = [c for c in cfg["columns"] if c in body]
    if not set_cols:
        return {"id": row_id, "updated": 0}
    assignments = ", ".join(f"{c} = {_col_expr(c)}" for c in set_cols) + ", updated_at = CURRENT_TIMESTAMP()"
    params = {"id": row_id, **{c: _coerce(c, body[c]) for c in set_cols}}
    sql = f"UPDATE {fq(table)} SET {assignments} WHERE id = @id"
    mutate_with_audit(sql, params, f"{table}.update", f"{identity.role}:{identity.id}", {"id": row_id, **body})
    return {"id": row_id, "updated": len(set_cols)}


@app.delete("/api/{table}/{row_id}", status_code=204)
def delete_row(table: str, row_id: str, identity: Identity = Depends(require_identity)):
    cfg = _table_cfg(table)
    _guard_table(identity, cfg)
    owner = bq.query_rows(f"SELECT athlete_id FROM {fq(table)} WHERE id = @id LIMIT 1", {"id": row_id})
    if not owner:
        raise HTTPException(404, "row not found")
    scope.assert_can_access_id(identity, owner[0]["athlete_id"])
    mutate_with_audit(
        f"DELETE FROM {fq(table)} WHERE id = @id", {"id": row_id},
        f"{table}.delete", f"{identity.role}:{identity.id}", {"id": row_id},
    )


# ---------------------------------------------------------------------------
# static frontend (declared last; /api/* already matched above)
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    f = FRONTEND_DIR / "index.html"
    if not f.exists():
        raise HTTPException(404, "frontend not found")
    return FileResponse(f, headers={"Cache-Control": "no-cache, must-revalidate"})

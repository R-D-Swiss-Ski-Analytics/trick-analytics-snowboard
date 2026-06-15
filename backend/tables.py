"""Per-table column contracts for the generic CRUD router.

`columns` is the whitelist of client-settable fields (server owns id, athlete_id,
athlet, created_by, created_at, updated_at). Anything not listed is ignored on
write — this whitelist IS the input validation.

`coach_only` tables are invisible/!writable to athlete tokens.
`order_by` is the default ordering for list reads.
"""

# columns that must bind as FLOAT64 / INT64 (everything else binds as STRING;
# `datum` is special-cased to DATE() in the SQL builder).
FLOAT_COLS = {"setup", "ausfuehrung", "landung", "gesamt",
              "lernkurve", "rail", "kicker", "halfpipe", "mental"}
INT_COLS = {"coach_rating"}

TABLES: dict[str, dict] = {
    "tricks": {
        "coach_only": False,
        "order_by": "datum DESC, created_at DESC",
        "columns": [
            "datum", "typ", "disziplin",
            "drehrichtung", "flips", "achse", "rotation", "absprung", "grab",
            "bringback", "style", "railart", "slideform", "slidevar",
            "inspin", "swap", "outspin",
            "setup", "ausfuehrung", "landung", "gesamt",
            "kommentar", "trickaufbau", "videolink", "gelandet",
        ],
    },
    "standort": {
        "coach_only": False,
        "order_by": "created_at DESC",
        "columns": [
            "datum", "disziplin", "trick_label",
            "drehrichtung", "flips", "achse", "rotation", "absprung", "grab",
            "bringback", "railart", "slideform", "slidevar",
            "inspin", "swap", "outspin",
            "notiz", "status", "coach_rating", "coach_kommentar", "coach_video",
        ],
    },
    "athlete_notebook": {
        "coach_only": False,
        "order_by": "created_at DESC",
        "columns": ["kat", "datum", "kommentar"],
    },
    "notebook": {
        "coach_only": True,
        "order_by": "created_at DESC",
        "columns": ["coach", "kat", "datum", "kommentar"],
    },
    "trainerurteil": {
        "coach_only": True,
        "order_by": "datum DESC",
        "columns": ["coach", "datum", "lernkurve", "rail", "kicker", "halfpipe", "mental", "notiz"],
    },
}

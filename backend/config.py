import os

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "swiss-ski-science-datahub")
BQ_LOCATION = os.getenv("BQ_LOCATION", "europe-west6")
DATASET = os.getenv("BQ_DATASET", "trick_collector")
MD5_SECRET_NAME = os.getenv("MD5_SECRET_NAME", "trick-collector-md5")

# MSWSK custom field that distinguishes snowboard freestyle from freeski within
# the shared Park & Pipe sport (sport_id=1). Set on both athletes and coaches.
# field_value 650 = "Snowboard Freestyle", 651 = "Freeski & Snowboard Freestyle".
SPORTART_FIELD_ID = int(os.getenv("SPORTART_FIELD_ID", "236"))
SNOWBOARD_OPTION_IDS = os.getenv("SNOWBOARD_OPTION_IDS", "650,651").split(",")


def fq(table: str) -> str:
    """Fully-qualify a table name in the app dataset."""
    return f"`{GCP_PROJECT_ID}.{DATASET}.{table}`"

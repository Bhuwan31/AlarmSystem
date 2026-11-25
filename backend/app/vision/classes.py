"""Image categories, decision-agent actions and the levels they map to."""

CLASSES = [
    "normal",              # normal environmental / road conditions
    "heavy_rain",          # visible heavy rainfall (rain streaks, spray, low visibility)
    "urban_flooding",      # standing water between buildings / in streets
    "river_flooding",      # river out of its banks, flooded fields
    "flash_flooding",      # fast, turbulent, debris-laden flow
    "road_waterlogging",   # water pooled on a road surface
    "rising_water",        # river or channel close to its banks / bridge deck
    "landslide",           # slope failure, debris on a road
    "uncertain",           # unrelated, too dark, blurred or ambiguous
]
LABELS = {
    "normal": "Normal conditions", "heavy_rain": "Heavy rainfall evidence", "urban_flooding": "Urban flooding",
    "river_flooding": "River flooding", "flash_flooding": "Flash flooding", "road_waterlogging": "Road waterlogging",
    "rising_water": "Rising water level", "landslide": "Landslide evidence", "uncertain": "Uncertain / insufficient evidence",
}
HAZARD_CLASSES = {"urban_flooding", "river_flooding", "flash_flooding", "road_waterlogging", "rising_water", "landslide", "heavy_rain"}
FLOOD_FAMILY = {"urban_flooding", "river_flooding", "flash_flooding", "road_waterlogging", "rising_water", "heavy_rain"}

ACTIONS = ["NO_ALERT", "MONITOR", "ISSUE_WATCH", "ISSUE_WARNING", "ISSUE_CRITICAL_ALERT", "REQUEST_ADDITIONAL_EVIDENCE"]
NO_ALERT, MONITOR, ISSUE_WATCH, ISSUE_WARNING, ISSUE_CRITICAL, REQUEST_EVIDENCE = range(6)

ALERT_LEVELS = ["NONE", "WATCH", "WARNING", "CRITICAL"]            # index = numeric level
ACTION_LEVEL = {NO_ALERT: 0, MONITOR: 0, ISSUE_WATCH: 1, ISSUE_WARNING: 2, ISSUE_CRITICAL: 3}
LEVEL_ACTION = {0: "NO_ALERT", 1: "ISSUE_WATCH", 2: "ISSUE_WARNING", 3: "ISSUE_CRITICAL_ALERT"}
RISK = {0: "LOW", 1: "MODERATE", 2: "HIGH", 3: "SEVERE"}


def disaster_type(cls: str) -> str:
    """Incident type used for grouping and messages."""
    return {"landslide": "LANDSLIDE", "flash_flooding": "FLASH_FLOOD", "river_flooding": "RIVER_FLOOD",
            "rising_water": "RIVER_FLOOD", "heavy_rain": "HEAVY_RAIN"}.get(cls, "FLOOD")

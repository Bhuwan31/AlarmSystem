from datetime import datetime, timezone

from app.adapters import dhm, gpm_imerg, open_meteo

RIVER = [{
    "name": " Jhimruk Khola at Pyuthan", "id": 5677, "stationIndex": "339.2", "basin": "West Rapti", "district": "PYUTHAN",
    "latitude": 28.084454, "longitude": 82.828611, "series_id": 34440,
    "waterLevel": {"datetime": "2026-10-15T19:05:00+00:00", "value": 2.37610006332},
    "status": "BELOW WARNING LEVEL", "warning_level": "4.5", "danger_level": "", "steady": "STEADY", "elevation": 755,
}]
RAIN = [{
    "name": " Arghakhanchi", "id": 304, "latitude": 27.885, "longitude": 83.1397, "basin": "West Rapti",
    "latest_observation": {"datetime": "2026-10-15T13:10:00+00:00", "value": 0},
    "averages": [{"interval": 1, "value": None}, {"interval": 24, "value": 12.5}], "status": "BELOW WARNING LEVEL",
}]


def test_parse_dhm_river():
    stations, obs = dhm.parse_river(RIVER)
    s = stations[0]
    assert s.name == "Jhimruk Khola at Pyuthan" and s.warning_level == 4.5 and s.danger_level is None
    assert obs[0].variable == "water_level_m" and abs(obs[0].value - 2.376) < 1e-3


def test_parse_dhm_rain():
    stations, obs = dhm.parse_rain(RAIN)
    assert stations[0].kind == "rain"
    by_var = {o.variable: o.value for o in obs}
    assert by_var == {"rain_1h_mm": None, "rain_24h_mm": 12.5}


def test_open_meteo_grid_and_parse():
    pts = open_meteo.grid_points([80.0, 26.3, 88.3, 30.5], 0.5)
    assert len(pts) == 9 * 17
    payload = [{"current": {"time": "2026-10-15T19:15", "temperature_2m": 14.7, "wind_speed_10m": 5.0,
                            "wind_direction_10m": 270, "precipitation": 0.2},
                "hourly": {"precipitation": [0.1, 0.4, None]}}]
    gp = open_meteo.parse_response(payload, pts[:1])[0]
    assert gp.temperature_c == 14.7 and gp.rain_24h_forecast_mm == 0.5 and gp.wind_dir_deg == 270


def test_imerg_url_and_ascii_parse():
    start = datetime(2026, 7, 20, 6, 30, tzinfo=timezone.utc)
    url = gpm_imerg.granule_url("GPM_3IMERGHHE.07", "V07B", start)
    assert url.endswith("/2026/201/3B-HHR-E.MS.MRG.3IMERG.20260720-S063000-E065959.0390.V07B.HDF5")
    lon0, lon1, lat0, lat1 = gpm_imerg.index_window([80.0, 26.3, 88.3, 30.5])
    assert (lon0, lat0) == (2600, 1163)
    text = "Dataset: x\nprecipitation[0][0], 1.0, 3.0, -9999.9\nprecipitation[0][1], 2.0, 2.0, 0.0\n"
    pts = gpm_imerg.parse_ascii(text, lon0, lat0, start, 0.5)
    # cells: lat 26.35/26.45 -> 26.25 bucket (values 1, 3, 2, 2), lat 26.55 -> 26.75 bucket (value 0)
    assert [(p.lat, p.lon, p.precipitation_mm) for p in pts] == [(26.25, 80.25, 2.0), (26.75, 80.25, 0.0)]


def test_warning_index_handles_both_datums():
    from app.api.public import warning_index
    assert warning_index(2.25, 4.5) == 0.5
    assert warning_index(1343.94, 1345.8) == 0.628
    assert warning_index(None, 4.5) is None


def test_heat_status_classes():
    from app.weather_point import heat_status
    assert heat_status([30, 31, 29], 30)["level"] == "NONE"
    assert heat_status([33, 31, 29], 30)["level"] == "HOT"
    assert heat_status([36, 37, 30], 34)["level"] == "HEATWAVE"
    assert heat_status([30, 31, 29], 41)["level"] == "HEATWAVE"
    assert heat_status([41, 38, 36], 39)["level"] == "EXTREME_HEAT"
    assert heat_status([None, None], None)["level"] == "NONE"

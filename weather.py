import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

API_URL = "https://api.open-meteo.com/v1/forecast"
CITIES = {
    "Bucharest": (44.4323, 26.1063),
    "Cluj-Napoca": (46.7712, 23.6236),
    "Brașov": (45.6579, 25.6012),
    "Iași": (47.1585, 27.6014),
    "Timișoara": (45.7489, 21.2087),
}
METRICS = {
    "temperature_2m_min": "°C",
    "temperature_2m_max": "°C",
    "precipitation_sum": "mm",
}


def session() -> requests.Session:
    client = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods={"GET"}, backoff_max=8)
    client.mount("https://", HTTPAdapter(max_retries=retry))
    return client


def validate(payload: dict, day: date) -> None:
    if not isinstance(payload, dict) or payload.get("utc_offset_seconds") != 0:
        raise ValueError("Expected a JSON object with a zero UTC offset")
    daily, units = payload.get("daily"), payload.get("daily_units")
    if not isinstance(daily, dict) or not isinstance(units, dict):
        raise ValueError("Missing daily data or units")
    days = [(day + timedelta(days=offset)).isoformat() for offset in range(3)]
    if daily.get("time") != days:
        raise ValueError("Expected three consecutive forecast dates")
    for metric, unit in METRICS.items():
        values = daily.get(metric)
        if units.get(metric) != unit or not isinstance(values, list) or len(values) != len(days):
            raise ValueError(f"Invalid daily array or unit for {metric}")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
            raise ValueError(f"Invalid numeric value for {metric}")
    if any(value < 0 for value in daily["precipitation_sum"]):
        raise ValueError("Precipitation must be nonnegative")
    if any(low > high for low, high in zip(daily["temperature_2m_min"], daily["temperature_2m_max"])):
        raise ValueError("Minimum temperature exceeds maximum temperature")


def extract(client: requests.Session, day: date) -> dict:
    cities = {}
    for city, (lat, lon) in CITIES.items():
        logging.info("Fetching %s for %s", city, day)
        response = client.get(API_URL, params={
            "latitude": lat, "longitude": lon, "daily": ",".join(METRICS),
            "timezone": "GMT", "temperature_unit": "celsius", "precipitation_unit": "mm",
            "start_date": day.isoformat(), "end_date": (day + timedelta(days=2)).isoformat(),
        }, timeout=(5, 20))
        response.raise_for_status()
        payload = response.json()
        validate(payload, day)
        cities[city] = payload
    captured_at = datetime.now(timezone.utc).isoformat()
    return {"forecast_start": day.isoformat(), "captured_at": captured_at, "cities": cities}


def save_snapshot(path: Path, snapshot: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump(snapshot, file, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            file.write("\n")
        except BaseException:
            file.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_snapshot(path: Path) -> dict:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    day = date.fromisoformat(snapshot["forecast_start"])
    captured_at = datetime.fromisoformat(snapshot["captured_at"])
    if captured_at.utcoffset() != timedelta(0):
        raise ValueError("Snapshot capture time must include a UTC offset of zero")
    cities = snapshot["cities"]
    if cities.keys() != CITIES.keys():
        raise ValueError("Snapshot must contain exactly the configured cities")
    for payload in cities.values():
        validate(payload, day)
    return snapshot

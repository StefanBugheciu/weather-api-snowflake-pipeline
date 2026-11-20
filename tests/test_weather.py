import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import requests

import main
import weather

DAY = date(2026, 1, 1)


def payload():
    return {
        "utc_offset_seconds": 0,
        "daily_units": weather.METRICS.copy(),
        "daily": {
            "time": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "temperature_2m_min": [-4, -3, -2],
            "temperature_2m_max": [1, 2, 3],
            "precipitation_sum": [0, 0.1, 2],
        },
    }


class WeatherTests(unittest.TestCase):
    def test_extracts_five_cities_with_timeout(self):
        client = MagicMock()
        client.get.return_value.json.side_effect = payload
        result = weather.extract(client, DAY)
        self.assertEqual(result["cities"].keys(), weather.CITIES.keys())
        self.assertEqual(client.get.call_count, 5)
        first_call = client.get.call_args_list[0]
        self.assertEqual(first_call.kwargs["timeout"], (5, 20))
        self.assertEqual(first_call.kwargs["params"]["end_date"], "2026-01-03")
        self.assertEqual(first_call.args, (weather.API_URL,))

    def test_http_error_aborts_batch(self):
        client = MagicMock()
        client.get.return_value.raise_for_status.side_effect = requests.HTTPError()
        with self.assertRaises(requests.HTTPError):
            weather.extract(client, DAY)
        client.get.return_value.json.assert_not_called()

    def test_retries_transient_get_failures(self):
        with weather.session() as client:
            retry = client.get_adapter(weather.API_URL).max_retries
            self.assertTrue(retry.is_retry("GET", 429))
            self.assertTrue(retry.is_retry("GET", 503))
            self.assertFalse(retry.is_retry("GET", 400))
            self.assertEqual(retry.total, 3)

    def test_rejects_invalid_weather(self):
        for metric, value in [("precipitation_sum", -1), ("precipitation_sum", True),
                              ("temperature_2m_min", None), ("temperature_2m_min", float("nan")),
                              ("temperature_2m_min", 100), ("time", "2026-01-04")]:
            with self.subTest(metric=metric, value=value):
                bad = payload()
                bad["daily"][metric][0] = value
                with self.assertRaises(ValueError):
                    weather.validate(bad, DAY)

    def test_snapshot_round_trip_and_revalidation(self):
        client = MagicMock()
        client.get.return_value.json.side_effect = payload
        snapshot = weather.extract(client, DAY)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.json"
            weather.save_snapshot(path, snapshot)
            self.assertEqual(weather.load_snapshot(path), snapshot)
            original = path.read_bytes()
            weather.save_snapshot(path, snapshot)
            self.assertEqual(path.read_bytes(), original)
            snapshot["cities"].pop("Iași")
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaises(ValueError):
                weather.load_snapshot(path)

    def test_ingest_binds_payload_and_commits_after_all_cities(self):
        connection = MagicMock()
        client = MagicMock()
        client.get.return_value.json.side_effect = payload
        main.ingest(connection, weather.extract(client, DAY))
        cursor = connection.cursor.return_value.__enter__.return_value
        self.assertEqual(cursor.execute.call_count, 6)
        self.assertEqual(json.loads(cursor.execute.call_args.args[1][-1]), payload())
        connection.commit.assert_called_once()

    def test_failed_ingest_rolls_back(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = [None, RuntimeError("load failure")]
        with self.assertRaises(RuntimeError):
            main.ingest(connection, {"forecast_start": DAY.isoformat(),
                                    "captured_at": "2026-01-01T00:00:00+00:00",
                                    "cities": {"Bucharest": payload()}})
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once()

"""Allow-listed, read-only public-data tools used before Qwen generation."""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "PTA-Wildfire-Research/1.0 (local research application)"
def _json(url: str, timeout: int = 12) -> dict[str, Any]:
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"}), timeout=timeout) as response:
        return json.load(response)

def _weather(lat: float, lon: float, target: date) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    base = "https://archive-api.open-meteo.com/v1/archive" if target < today - timedelta(days=5) else "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon, "start_date": target.isoformat(), "end_date": target.isoformat(), "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_min", "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch", "timezone": "auto"}
    daily = _json(base + "?" + urlencode(params)).get("daily", {})
    return {k: (v[0] if isinstance(v, list) and v else v) for k, v in daily.items()}

def _nws_alerts(lat: float, lon: float) -> list[dict[str, Any]]:
    data = _json(f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}")
    alerts = []
    for feature in data.get("features", [])[:10]:
        p = feature.get("properties", {})
        if any(word in (p.get("event") or "").lower() for word in ("fire", "wind", "heat", "red flag")):
            alerts.append({k: p.get(k) for k in ("event", "severity", "urgency", "headline", "effective", "expires", "web")})
    return alerts

def collect_fire_context(lat: float, lon: float, date_text: str) -> dict[str, Any]:
    target = date.fromisoformat(date_text)
    result: dict[str, Any] = {"weather_for_requested_date": None, "active_nws_alerts_now": None, "errors": [], "sources": [{"title": "Open-Meteo weather API", "url": "https://open-meteo.com/en/docs"}, {"title": "National Weather Service active alerts", "url": "https://www.weather.gov/documentation/services-web-api"}]}
    try: result["weather_for_requested_date"] = _weather(lat, lon, target)
    except Exception as exc: result["errors"].append(f"Weather tool unavailable or date outside coverage: {exc}")
    try: result["active_nws_alerts_now"] = _nws_alerts(lat, lon)
    except Exception as exc: result["errors"].append(f"NWS alerts tool unavailable: {exc}")
    return result

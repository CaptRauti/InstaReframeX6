"""gpx_parser.py — stdlib GPX parser (xml.etree, no deps).

Parses <trkpt>/<wpt> into points with UTC time, lat, lon, ele.
Speed and bearing are derived per point (haversine / dt, great-circle bearing).
"""
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List


@dataclass
class GpxPoint:
    time: datetime      # UTC-aware
    lat: float
    lon: float
    ele: float          # altitude, metres
    speed: float = 0.0  # m/s, derived (or GPX ext)
    bearing: float = 0.0  # degrees, 0=N, clockwise


def _parse_time(s):
    s = s.strip()
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def parse_gpx(path):
    """Return sorted list of GpxPoint from trkpts (falls back to wpts)."""
    ns = ""
    root = ET.parse(path).getroot()
    # namespace-tolerant search
    pts = []
    for tag in ("trkpt", "wpt", "rtept"):
        for el in root.iter():
            if el.tag.endswith(tag):
                lat = float(el.get("lat"))
                lon = float(el.get("lon"))
                t = None
                e = 0.0
                for c in el:
                    if c.tag.endswith("time"):
                        t = _parse_time(c.text)
                    elif c.tag.endswith("ele"):
                        e = float(c.text)
                if t is None:
                    continue
                pts.append(GpxPoint(t, lat, lon, e))
    pts.sort(key=lambda p: p.time)
    # derive speed/bearing from successive points
    for i in range(len(pts)):
        if i == 0:
            pts[i].speed = 0.0
            pts[i].bearing = 0.0
            continue
        prev = pts[i - 1]
        dt = (pts[i].time - prev.time).total_seconds()
        if dt > 0:
            d = haversine(prev.lat, prev.lon, pts[i].lat, pts[i].lon)
            pts[i].speed = d / dt
            pts[i].bearing = bearing(prev.lat, prev.lon, pts[i].lat, pts[i].lon)
        else:
            pts[i].speed = pts[i - 1].speed
            pts[i].bearing = pts[i - 1].bearing
    return pts
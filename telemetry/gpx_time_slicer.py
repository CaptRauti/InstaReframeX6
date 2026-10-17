"""gpx_time_slicer.py — core: slice a master GPX to a clip's UTC time window
and interpolate telemetry frame-by-frame at the target FPS.

Frame-accurate model:
    frame i  ->  t_i = clip_start + offset + i / fps   (absolute UTC)
GPX points outside [start+offset, start+offset+duration] are dropped.
Interpolation is linear on the time axis; heading is interpolated via
sin/cos decomposition so 359°->1° never wraps through 180°.
"""
import math
from dataclasses import dataclass
from datetime import timezone
from typing import List
import numpy as np

from .gpx_parser import GpxPoint, parse_gpx
from .metadata import clip_start_utc, probe_video


@dataclass
class TelemetryFrame:
    frame: int
    t_rel: float        # seconds from clip start
    speed_kmh: float
    speed_mph: float
    alt: float
    heading: float      # degrees, 0..360
    lat: float
    lon: float


def _to_epoch(dt):
    return dt.timestamp()


def interpolate_track(points: List[GpxPoint], t_grid: np.ndarray):
    """Frame-accurate linear interpolation of speed/alt/lat/lon/heading.

    t_grid: absolute epoch seconds per frame.
    Returns list of dicts per frame.
    """
    if not points:
        return [None] * len(t_grid)
    t_pts = np.array([_to_epoch(p.time) for p in points])
    speed = np.array([p.speed for p in points])
    alt = np.array([p.ele for p in points])
    lat = np.array([p.lat for p in points])
    lon = np.array([p.lon for p in points])
    head = np.radians([p.bearing for p in points])

    out = []
    for t in t_grid:
        if t <= t_pts[0]:
            i = 0
        elif t >= t_pts[-1]:
            i = len(t_pts) - 1
        else:
            i = int(np.searchsorted(t_pts, t)) - 1
        t0, t1 = t_pts[i], t_pts[i + 1]
        f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
        lin = lambda a: float(a[i] + (a[i + 1] - a[i]) * f)
        # heading: sin/cos interpolation (wrap-safe)
        s = math.sin(head[i]) + (math.sin(head[i + 1]) - math.sin(head[i])) * f
        c = math.cos(head[i]) + (math.cos(head[i + 1]) - math.cos(head[i])) * f
        h = (math.degrees(math.atan2(s, c)) + 360.0) % 360.0
        out.append({
            "speed": lin(speed), "alt": lin(alt),
            "lat": lin(lat), "lon": lin(lon), "heading": h,
        })
    return out


def slice_gpx(gpx_path, video_path, offset_s=0.0, fps=None):
    """Slice master GPX to the clip window; return TelemetryFrame list.

    offset_s: manual sync drift correction applied to the clip clock.
    fps: target FPS (default: the clip's own r_frame_rate).
    """
    points = parse_gpx(gpx_path)
    start, src = clip_start_utc(video_path)
    info = probe_video(video_path)
    fps = fps or info["fps"] or 30.0
    duration_s = info["duration_ms"] / 1000.0
    n_frames = info["nb_frames"] or int(round(duration_s * fps))

    t_start = _to_epoch(start) + offset_s
    t_grid = t_start + np.arange(n_frames) / fps

    # filter master GPX to [start+offset, start+offset+duration]
    lo, hi = t_start, t_start + duration_s
    window = [p for p in points if lo <= _to_epoch(p.time) <= hi]
    # keep neighbours outside the window for interpolation anchors
    anchors = [p for p in points if _to_epoch(p.time) < lo]
    anchors = anchors[-1:] if anchors else []
    tail = [p for p in points if _to_epoch(p.time) > hi]
    tail = tail[:1] if tail else []
    track = anchors + window + tail

    vals = interpolate_track(track, t_grid)
    frames = []
    for i, v in enumerate(vals):
        if v is None:
            continue
        frames.append(TelemetryFrame(
            frame=i, t_rel=i / fps,
            speed_kmh=v["speed"] * 3.6,
            speed_mph=v["speed"] * 2.236936,
            alt=v["alt"], heading=v["heading"],
            lat=v["lat"], lon=v["lon"],
        ))
    return frames, {"start_utc": start.isoformat(), "start_source": src,
                    "fps": fps, "duration_ms": info["duration_ms"],
                    "frames": n_frames, "offset_s": offset_s}

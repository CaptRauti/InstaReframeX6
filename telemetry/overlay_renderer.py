"""overlay_renderer.py — Strategy A: transparent dashboard overlay video.

Renders every frame on a 100% transparent RGBA canvas (speedometer gauge,
speed km/h + mph, altitude, coordinates, compass, mini track map) and exports
via FFmpeg as ProRes 4444 (yuva444p10le) or QTRLE (rgba) MOV with alpha.

Deps: Pillow, numpy, ffmpeg. Background is RGBA(0,0,0,0) everywhere.
"""
import os
import math
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "C:/Windows/Fonts/segoeui.ttf"
FONT_BOLD = "C:/Windows/Fonts/segoeui.ttf"


def _font(size, bold=False):
    return ImageFont.truetype(FONT_PATH, size)


def draw_frame(telemetry, canvas_w, canvas_h, track_pts, style):
    """Draw one dashboard frame. Returns RGBA PIL image (transparent bg)."""
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = style.get("accent", (0, 200, 255, 255))
    dim = style.get("dim", (180, 180, 180, 200))

    # ---------- speedometer gauge (bottom-right) ----------
    cx, cy = canvas_w - 180, canvas_h - 170
    r = 110
    max_kmh = style.get("max_kmh", 120.0)
    a0, a1 = 240.0, 420.0  # gauge sweep degrees (270° arc)
    # arc background
    d.arc([cx - r, cy - r, cx + r, cy + r], start=a0, end=a1,
          fill=(60, 60, 60, 160), width=10)
    # value arc
    frac = min(1.0, telemetry["speed_kmh"] / max_kmh)
    end = a0 + (a1 - a0) * frac
    d.arc([cx - r, cy - r, cx + r, cy + r], start=a0, end=end, fill=col, width=10)
    # needle
    ang = math.radians(a0 + (a1 - a0) * frac)
    nx, ny = cx + math.cos(ang) * (r - 20), cy + math.sin(ang) * (r - 20)
    d.line([cx, cy, nx, ny], fill=col, width=4)
    d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=col)
    # speed text
    f_big = _font(52)
    txt = "%d" % round(telemetry["speed_kmh"])
    w = d.textlength(txt, font=f_big)
    d.text((cx - w / 2, cy + 18), txt, font=f_big, fill=(255, 255, 255, 255))
    f_small = _font(22)
    d.text((cx - 34, cy + 72), "km/h", font=f_small, fill=dim)
    d.text((cx - 70, cy - r - 30), "%.1f mph" % telemetry["speed_mph"],
           font=f_small, fill=dim)

    # ---------- compass (heading) ----------
    hx, hy = cx - 200, cy
    hr = 34
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], outline=col, width=3)
    ha = math.radians(telemetry["heading"] - 90.0)  # 0°=up
    d.line([hx, hy, hx + math.cos(ha) * (hr - 6), hy + math.sin(ha) * (hr - 6)],
           fill=col, width=4)
    d.text((hx - 16, hy + hr + 4), "%d°" % round(telemetry["heading"]),
           font=f_small, fill=dim)

    # ---------- info panel (top-right) ----------
    f_info = _font(26)
    lines = [
        "ALT %5.0f m" % telemetry["alt"],
        "LAT  %8.5f" % telemetry["lat"],
        "LON  %8.5f" % telemetry["lon"],
    ]
    y = 30
    for ln in lines:
        d.text((canvas_w - 340, y), ln, font=f_info, fill=(255, 255, 255, 220))
        y += 34

    # ---------- mini track map (top-left) ----------
    if len(track_pts) > 1:
        mx, my, mw, mh = 30, 30, 200, 200
        lats = [p[0] for p in track_pts]
        lons = [p[1] for p in track_pts]
        lat0, lat1 = min(lats), max(lats)
        lon0, lon1 = min(lons), max(lons)
        sx = mw / max(1e-9, (lon1 - lon0))
        sy = mh / max(1e-9, (lat1 - lat0))
        def norm(p):
            return (mx + (p[1] - lon0) * sx, my + mh - (p[0] - lat0) * sy)
        d.rectangle([mx, my, mx + mw, my + mh], outline=(90, 90, 90, 160), width=2)
        d.line([norm(p) for p in track_pts], fill=(255, 255, 255, 160), width=3)
        # current position dot
        cur = norm((telemetry["lat"], telemetry["lon"]))
        d.ellipse([cur[0] - 5, cur[1] - 5, cur[0] + 5, cur[1] + 5], fill=col)

    return img


def render_overlay(frames, track_pts, out_path, canvas_w=1920, canvas_h=1080,
                   codec="prores", style=None, fps=None):
    """Render TelemetryFrame list -> transparent MOV (ProRes 4444 / QTRLE).

    frames: list of TelemetryFrame (slicer output)
    track_pts: [(lat, lon), ...] for the mini map
    codec: 'prores' (yuva444p10le) or 'qtrle' (rgba)
    fps: target frame rate (default: derived from frame spacing)
    Returns (out_path, ffmpeg_rc).
    """
    style = style or {"accent": (0, 200, 255, 255), "max_kmh": 120.0}
    if fps is None:
        if len(frames) > 1:
            fps = 1.0 / (frames[1].t_rel - frames[0].t_rel)
        else:
            fps = 30.0
    fps = round(fps, 6)

    frames_dir = out_path + "_frames"
    os.makedirs(frames_dir, exist_ok=True)
    for i, fr in enumerate(frames):
        img = draw_frame({"speed_kmh": fr.speed_kmh,
                          "speed_mph": fr.speed_mph,
                          "alt": fr.alt, "heading": fr.heading,
                          "lat": fr.lat, "lon": fr.lon},
                         canvas_w, canvas_h, track_pts, style)
        img.save(os.path.join(frames_dir, "frame%06d.png" % i))

    # FFmpeg: image2 sequence -> alpha MOV
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-framerate", str(fps),
           "-i", os.path.join(frames_dir, "frame%06d.png")]
    if codec == "prores":
        cmd += ["-c:v", "prores_ks", "-profile:v", "4444",
                "-pix_fmt", "yuva444p10le"]
    else:
        cmd += ["-c:v", "qtrle", "-pix_fmt", "rgba"]
    cmd += [out_path]
    rc = subprocess.run(cmd, capture_output=True, text=True).returncode
    return out_path, rc

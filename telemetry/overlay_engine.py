#!/usr/bin/env python3
"""InstaReframeX6 telemetry overlay engine (Strategy A).

Input: GPX (from Insta360 Studio export) + clip start time.
Output: transparent overlay MOV (qtrle RGBA) matching clip fps/resolution,
        plus telemetry.json (interpolated per-frame values for Fusion/Strategy B).

Usage:
  python overlay_engine.py --gpx track.gpx --start 2026-09-27T08:46:02Z \
      --fps 50 --frames 2350 --width 1080 --height 1920 --out overlay.mov
"""
import argparse, json, math, os, sys, subprocess, datetime as dt
from xml.etree import ElementTree as ET

def parse_gpx(path):
    ns = "{http://www.topografix.com/GPX/1/1}"
    root = ET.parse(path).getroot()
    pts = []
    for trkpt in root.iter(f"{ns}trkpt"):
        t = trkpt.find(f"{ns}time")
        if t is None: continue
        ts = dt.datetime.strptime(t.text.strip(), "%Y-%m-%dT%H:%M:%S%z")
        pts.append((ts.timestamp(), float(trkpt.get("lat")), float(trkpt.get("lon")),
                    float(trkpt.find(f"{ns}ele").text) if trkpt.find(f"{ns}ele") is not None else 0.0))
    pts.sort()
    return pts

def haversine(a, b):
    R = 6371000.0
    lat1, lon1, lat2, lon2 = map(math.radians, [a[1], a[2], b[1], b[2]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(h))

def bearing(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a[1], a[2], b[1], b[2]])
    dlon = lon2 - lon1
    x = math.sin(dlon)*math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360

def metrics(pts):
    """per trackpoint: speed m/s, heading deg, altitude m, cumulative distance m"""
    out = []
    dist = 0.0
    for i, p in enumerate(pts):
        if i == 0:
            sp, hd = 0.0, 0.0
        else:
            dtv = p[0] - pts[i-1][0]
            sp = haversine(pts[i-1], p) / dtv if dtv > 0 else 0.0
            hd = bearing(pts[i-1], p) if sp > 0.1 else (out[-1][2] if out else 0.0)
            dist += haversine(pts[i-1], p)
        out.append((p[0], sp, hd, p[3], dist))
    return out

def interpolate(ms, t):
    """linear interpolation of metrics list [(t, speed, heading, ele, dist)] at time t"""
    if t <= ms[0][0]: return ms[0]
    if t >= ms[-1][0]: return ms[-1]
    lo, hi = 0, len(ms)-1
    while hi - lo > 1:
        mid = (lo+hi)//2
        if ms[mid][0] <= t: lo = mid
        else: hi = mid
    a, b = ms[lo], ms[hi]
    f = (t - a[0]) / (b[0] - a[0])
    # heading interpolates on shortest arc
    dh = (b[2] - a[2] + 180) % 360 - 180
    return (t, a[1]+f*(b[1]-a[1]), (a[2]+f*dh) % 360, a[3]+f*(b[3]-a[3]), a[4]+f*(b[4]-a[4]))

def render_frames(ms, start_ts, fps, frames, width, height, outdir):
    from PIL import Image, ImageDraw, ImageFont
    fdir = os.path.join(os.path.dirname(__file__), "fonts")
    font_path = None
    for cand in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(cand): font_path = cand; break
    fs_big = int(height*0.045); fs_small = int(height*0.028)
    font = ImageFont.truetype(font_path, fs_big)
    font2 = ImageFont.truetype(font_path, fs_small)
    os.makedirs(outdir, exist_ok=True)
    for i in range(frames):
        t = start_ts + i/fps
        _, sp, hd, ele, dist = interpolate(ms, t)
        img = Image.new("RGBA", (width, height), (0,0,0,0))
        d = ImageDraw.Draw(img)
        # layout: bottom-left stack, 9:16 friendly
        x = int(width*0.06); y = int(height*0.82)
        d.text((x, y), f"{sp*3.6:.1f} km/h", font=font, fill=(255,255,255,230))
        d.text((x, y+fs_big+8), f"{ele:.0f} m  {dist/1000:.2f} km", font=font2, fill=(200,200,200,200))
        # heading arrow
        cx = int(width*0.88); cy = int(height*0.87); r = int(width*0.08)
        a = math.radians(hd-90)
        d.ellipse((cx-r, cy-r, cx+r, cy+r), outline=(255,255,255,160), width=max(2,int(width/270)))
        d.line((cx, cy, cx+r*math.cos(a), cy+r*math.sin(a)), fill=(255,255,255,230), width=max(3,int(width/180)))
        img.save(os.path.join(outdir, f"f{i:06d}.png"))

def encode(outdir, fps, out_mov):
    subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-framerate",str(fps),
        "-i", os.path.join(outdir,"f%06d.png"), "-vf","format=rgba","-c:v","qtrle", out_mov],
        check=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpx", required=True)
    ap.add_argument("--start", required=True)  # ISO clip start, e.g. 2026-09-27T08:46:02Z
    ap.add_argument("--fps", type=float, default=50)
    ap.add_argument("--frames", type=int, default=2350)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--out", default="overlay.mov")
    a = ap.parse_args()
    start_ts = dt.datetime.strptime(a.start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    ms = metrics(parse_gpx(a.gpx))
    json.dump({"fps": a.fps, "start": start_ts,
               "per_frame": [list(interpolate(ms, start_ts+i/a.fps)) for i in range(a.frames)]},
              open(os.path.splitext(a.out)[0]+".json","w"))
    render_frames(ms, start_ts, a.fps, a.frames, a.width, a.height, os.path.splitext(a.out)[0]+"_frames")
    encode(os.path.splitext(a.out)[0]+"_frames", a.fps, a.out)
    print("OK", a.out)

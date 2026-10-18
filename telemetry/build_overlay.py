#!/usr/bin/env python3
"""InstaReframeX6 telemetry pipeline — Strategy A end-to-end.

Clip-driven workflow:
  1. Sidecar GPX: put <name>.gpx next to the clip (same folder, e.g.
     VID_20260927_084602_00_058.gpx next to VID_20260927_084602_00_058.mp4,
     or any *.gpx in the clip folder).
  2. Clip start time is taken from the filename (VID_YYYYMMDD_HHMMSS),
     interpreted as camera-local time (use --tz for offset to GPX UTC).
  3. Engine renders a transparent overlay clip (qtrle RGBA MOV) at the
     clip's fps and the target dashboard resolution, covering the full clip
     duration, with per-frame interpolated telemetry.
  4. Optional: --timeline builds/extends the Resolve timeline so video and
     overlay are frame-synced (overlay on top track).

Layouts (--layout):
  minimal : speed + heading arrow
  full    : speed, altitude, distance, heading arrow, trail minimap
  map     : trail minimap + speed

Usage:
  python build_overlay.py --clip D:/X6/.../VID_20260927_084602_00_058.mp4 \
      [--gpx path.gpx] [--layout full] [--width 1080 --height 1920] \
      [--tz 2] [--timeline]
"""
import argparse, glob, json, math, os, re, subprocess, sys, datetime as dt
from xml.etree import ElementTree as ET

FFMPEG = r"C:/Users/stefa/AppData/Local/hermes/tools/ffmpeg-9.0.1-win32-x64/bin/ffmpeg.exe"

def clip_start_from_name(name):
    m = re.search(r"VID_(\d{8})_(\d{6})", name)
    if not m: return None
    d, t = m.group(1), m.group(2)
    return dt.datetime(int(d[0:4]), int(d[4:6]), int(d[6:8]),
                       int(t[0:2]), int(t[2:4]), int(t[4:6]))

def clip_fps_duration(path):
    out = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True)
    m = re.search(r"(\d+) fps", out.stderr)
    fps = int(m.group(1)) if m else 50
    m2 = re.search(r"Duration: (\d+):(\d+):(\d+)\.(\d+)", out.stderr)
    dur = 0
    if m2:
        h, mi, s, f = map(int, m2.groups())
        dur = h*3600 + mi*60 + s + f/100.0
    return fps, dur

def parse_gpx(path):
    ns = "{http://www.topografix.com/GPX/1/1}"
    root = ET.parse(path).getroot()
    pts = []
    for trkpt in root.iter(f"{ns}trkpt"):
        t = trkpt.find(f"{ns}time")
        if t is None: continue
        txt = t.text.strip()
        ts = dt.datetime.fromisoformat(txt.replace("Z", "+00:00"))
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
    out, dist = [], 0.0
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
    if t <= ms[0][0]: return ms[0]
    if t >= ms[-1][0]: return ms[-1]
    lo, hi = 0, len(ms)-1
    while hi - lo > 1:
        mid = (lo+hi)//2
        if ms[mid][0] <= t: lo = mid
        else: hi = mid
    a, b = ms[lo], ms[hi]
    f = (t - a[0]) / (b[0] - a[0])
    dh = (b[2] - a[2] + 180) % 360 - 180
    return (t, a[1]+f*(b[1]-a[1]), (a[2]+f*dh) % 360, a[3]+f*(b[3]-a[3]), a[4]+f*(b[4]-a[4]))

def trail_polyline(pts, t, window=120, scale=1.0):
    """lat/lon of trail points within window seconds, centered on position at t"""
    ref = None
    for p in pts:
        if p[0] >= t: ref = p; break
    if ref is None: ref = pts[-1]
    out = []
    for p in pts:
        if t - window <= p[0] <= t + 2:
            dlat = p[1] - ref[1]
            dlon = p[2] - ref[2]
            out.append((dlat*111320.0*scale, dlon*111320.0*math.cos(math.radians(ref[1]))*scale))
    return out

def render(ms, pts, start_ts, fps, frames, width, height, layout, outdir):
    from PIL import Image, ImageDraw, ImageFont
    font_path = "C:/Windows/Fonts/segoeui.ttf"
    if not os.path.exists(font_path): font_path = "C:/Windows/Fonts/arial.ttf"
    fs_big = int(height*0.045); fs_small = int(height*0.028)
    font = ImageFont.truetype(font_path, fs_big)
    font2 = ImageFont.truetype(font_path, fs_small)
    os.makedirs(outdir, exist_ok=True)
    for i in range(frames):
        t = start_ts + i/fps
        _, sp, hd, ele, dist = interpolate(ms, t)
        img = Image.new("RGBA", (width, height), (0,0,0,0))
        d = ImageDraw.Draw(img)
        x = int(width*0.06); y = int(height*0.82)
        d.text((x, y), f"{sp*3.6:.1f} km/h", font=font, fill=(255,255,255,230))
        if layout in ("full",):
            d.text((x, y+fs_big+8), f"{ele:.0f} m  {dist/1000:.2f} km", font=font2, fill=(200,200,200,200))
        # compass
        cx = int(width*0.88); cy = int(height*0.87); r = int(width*0.08)
        a = math.radians(hd-90)
        d.ellipse((cx-r, cy-r, cx+r, cy+r), outline=(255,255,255,160), width=max(2,int(width/270)))
        d.line((cx, cy, cx+r*math.cos(a), cy+r*math.sin(a)), fill=(255,255,255,230), width=max(3,int(width/180)))
        if layout in ("full", "map"):
            # trail minimap top-right
            mcx = int(width*0.85); mcy = int(height*0.12); sc = width/600.0
            poly = trail_polyline(pts, t, window=120, scale=sc)
            if len(poly) > 1:
                d.line([(mcx+px, mcy-py) for px, py in poly], fill=(255,255,255,140), width=max(2,int(width/300)))
                d.ellipse((mcx-4, mcy-4, mcx+4, mcy+4), fill=(255,80,80,230))
        img.save(os.path.join(outdir, f"f{i:06d}.png"))

def encode(outdir, fps, out_mov):
    subprocess.run([FFMPEG,"-y","-hide_banner","-loglevel","error","-framerate",str(fps),
        "-i", os.path.join(outdir,"f%06d.png"), "-vf","format=rgba","-c:v","qtrle", out_mov],
        check=True)

def build_timeline(clip_path, overlay_path):
    RESOLVE_SCRIPT_API="C:/ProgramData/Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting"
    RESOLVE_SCRIPT_LIB="C:/Program Files/Blackmagic Design/DaVinci Resolve/fusionscript.dll"
    PYTHONPATH="C:/ProgramData/Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting/Modules"
    import os as _os
    _os.environ["RESOLVE_SCRIPT_API"]=RESOLVE_SCRIPT_API
    _os.environ["RESOLVE_SCRIPT_LIB"]=RESOLVE_SCRIPT_LIB
    _os.environ["PYTHONPATH"]=PYTHONPATH
    sys.path.append(PYTHONPATH)
    import DaVinciResolveScript as dvr
    app=dvr.scriptapp("Resolve")
    pm=app.GetProjectManager()
    proj=pm.LoadProject("OFX_Test")
    mp=proj.GetMediaPool()
    items=mp.ImportMedia([clip_path, overlay_path])
    mp.CreateEmptyTimeline("Telemetry_"+os.path.basename(clip_path))
    tl=None
    for i in range(proj.GetTimelineCount(), 0, -1):
        t=proj.GetTimelineByIndex(i)
        if t and (t.GetName() or "").startswith("Telemetry_"): tl=t; break
    if not tl: sys.exit("timeline not created")
    proj.SetCurrentTimeline(tl)
    mp.AppendToTimeline([{"mediaPoolItem": items[0], "startFrame":0, "trackIndex":1, "recordFrame":0}])
    mp.AppendToTimeline([{"mediaPoolItem": items[1], "startFrame":0, "trackIndex":2, "recordFrame":0}])
    print("timeline built", tl.GetName())

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True)
    ap.add_argument("--gpx", default=None)
    ap.add_argument("--layout", default="full", choices=["minimal","full","map"])
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--tz", type=int, default=2, help="camera-local -> UTC offset hours")
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--timeline", action="store_true")
    a = ap.parse_args()

    clip_dir = os.path.dirname(a.clip)
    gpx = a.gpx
    if not gpx:
        base = os.path.splitext(os.path.basename(a.clip))[0]
        cand = os.path.join(clip_dir, base + ".gpx")
        if os.path.exists(cand): gpx = cand
        else:
            found = glob.glob(os.path.join(clip_dir, "*.gpx"))
            gpx = found[0] if found else None
    if not gpx:
        sys.exit("no sidecar .gpx found next to clip")

    start_local = clip_start_from_name(os.path.basename(a.clip))
    if not start_local:
        sys.exit("cannot parse start time from clip filename")
    start_ts = (start_local - dt.timedelta(hours=a.tz)).replace(tzinfo=dt.timezone.utc).timestamp()

    fps, dur = clip_fps_duration(a.clip)
    frames = a.frames if a.frames else int(round(dur*fps))
    out = a.out or os.path.join(clip_dir, os.path.splitext(os.path.basename(a.clip))[0] + "_overlay.mov")

    ms = metrics(parse_gpx(gpx))
    pts = parse_gpx(gpx)
    json.dump({"fps": fps, "start_utc": start_ts, "clip": a.clip, "gpx": gpx,
               "per_frame": [list(interpolate(ms, start_ts+i/fps)) for i in range(frames)]},
              open(os.path.splitext(out)[0]+".json","w"))
    render(ms, pts, start_ts, fps, frames, a.width, a.height, a.layout,
           os.path.splitext(out)[0]+"_frames")
    encode(os.path.splitext(out)[0]+"_frames", fps, out)
    print("OK", out, frames, "frames", fps, "fps")
    if a.timeline:
        build_timeline(a.clip, out)

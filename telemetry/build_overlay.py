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

def pan_from_spec(spec, t):
    """spec: list of (t, pan) keyframes, linear interp, wrap 360"""
    if not spec: return 0.0
    if t <= spec[0][0]: return spec[0][1]
    if t >= spec[-1][0]: return spec[-1][1]
    lo, hi = 0, len(spec)-1
    while hi - lo > 1:
        mid = (lo+hi)//2
        if spec[mid][0] <= t: lo = mid
        else: hi = mid
    a, b = spec[lo], spec[hi]
    f = (t - a[0]) / (b[0] - a[0])
    return (a[1] + f*(b[1] - a[1])) % 360

def parse_pan_log(path):
    """Extract pan(t) from OFX render log lines 'render t=... pan=...'"""
    spec = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        m = re.search(r"render t=([\d.]+).*?pan=([-\d.]+)", line)
        if m: spec.append((float(m.group(1)), float(m.group(2))))
    spec.sort()
    # dedupe consecutive identical t
    out = []
    for t, p in spec:
        if out and abs(out[-1][0] - t) < 1e-6: out[-1] = (t, p)
        else: out.append((t, p))
    return out

def parse_pan(s):
    """'0:0,59:180' -> [(0,0),(59,180)]"""
    out = []
    for part in s.split(","):
        t, p = part.split(":")
        out.append((float(t), float(p)))
    out.sort()
    return out

def render(ms, pts, start_ts, fps, frames, width, height, layout, outdir, pan_spec=None):
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
        pan = pan_from_spec(pan_spec, t - start_ts) if pan_spec else 0.0
        img = Image.new("RGBA", (width, height), (0,0,0,0))
        if layout == "holo":
            render_holo(img, width, height, sp, hd, ele, dist, pan, pts, t, font, font2)
        else:
            d = ImageDraw.Draw(img)
            x = int(width*0.06); y = int(height*0.82)
            d.text((x, y), f"{sp*3.6:.1f} km/h", font=font, fill=(255,255,255,230))
            if layout in ("full",):
                d.text((x, y+fs_big+8), f"{ele:.0f} m  {dist/1000:.2f} km", font=font2, fill=(200,200,200,200))
            cx = int(width*0.88); cy = int(height*0.87); r = int(width*0.08)
            a = math.radians(hd-90)
            d.ellipse((cx-r, cy-r, cx+r, cy+r), outline=(255,255,255,160), width=max(2,int(width/270)))
            d.line((cx, cy, cx+r*math.cos(a), cy+r*math.sin(a)), fill=(255,255,255,230), width=max(3,int(width/180)))
            if layout in ("full", "map"):
                mcx = int(width*0.85); mcy = int(height*0.12); sc = width/600.0
                poly = trail_polyline(pts, t, window=120, scale=sc)
                if len(poly) > 1:
                    d.line([(mcx+px, mcy-py) for px, py in poly], fill=(255,255,255,140), width=max(2,int(width/300)))
                    d.ellipse((mcx-4, mcy-4, mcx+4, mcy+4), fill=(255,80,80,230))
        img.save(os.path.join(outdir, f"f{i:06d}.png"))

def render_holo(img, width, height, sp, hd, ele, dist, pan, pts, t, font, font2):
    """Holographic dashboard anchored to world orientation:
    ring of cardinal directions rotates with pan, trail minimap heading-up,
    glowing cyan strokes, corner brackets."""
    from PIL import Image, ImageDraw, ImageFilter
    glow = Image.new("RGBA", (width, height), (0,0,0,0))
    sharp = Image.new("RGBA", (width, height), (0,0,0,0))
    dg = ImageDraw.Draw(glow)
    ds = ImageDraw.Draw(sharp)
    cyan = (0, 220, 255, 200)
    white = (235, 250, 255, 235)
    lw = max(2, width//300)

    # --- compass ring, center bottom, rotates so world bearing b appears at screen angle b-pan
    cx = width/2.0; cy = height*0.80; R = width*0.32
    for b in range(0, 360, 15):
        a = math.radians(b - pan - 90)
        r1 = R*(0.92 if b % 45 else 0.86)
        x1 = cx + r1*math.cos(a); y1 = cy + r1*math.sin(a)
        x2 = cx + R*math.cos(a); y2 = cy + R*math.sin(a)
        ds.line((x1, y1, x2, y2), fill=cyan, width=lw)
    # ring circle
    ds.ellipse((cx-R, cy-R, cx+R, cy+R), outline=cyan, width=lw)
    # cardinal labels N/E/S/W
    for b, lab in ((0,"N"),(90,"O"),(180,"S"),(270,"W")):
        a = math.radians(b - pan - 90)
        lx = cx + R*1.10*math.cos(a); ly = cy + R*1.10*math.sin(a)
        ds.text((lx-10, ly-14), lab, font=font2, fill=white)
    # heading pointer (travel direction)
    a = math.radians(hd - pan - 90)
    ds.line((cx, cy, cx + R*0.8*math.cos(a), cy + R*0.8*math.sin(a)), fill=(255,90,90,230), width=max(3, width//180))
    ds.ellipse((cx-3, cy-3, cx+3, cy+3), fill=white)

    # --- speed text, center, glowing
    txt = f"{sp*3.6:.1f} km/h"
    tb = ds.textbbox((0,0), txt, font=font)
    tw = tb[2]-tb[0]
    tx = (width-tw)/2; ty = height*0.62
    ds.text((tx, ty), txt, font=font, fill=white)
    dg.text((tx, ty), txt, font=font, fill=cyan)
    # data line under speed
    sub = f"{ele:.0f} m  {dist/1000:.2f} km  {hd:.0f}°"
    tb2 = ds.textbbox((0,0), sub, font=font2)
    sx = (width-(tb2[2]-tb2[0]))/2
    ds.text((sx, ty+int(height*0.045)+10), sub, font=font2, fill=(180,230,255,210))
    dg.text((sx, ty+int(height*0.045)+10), sub, font=font2, fill=cyan)

    # --- trail minimap, heading-up (rotate trail by -hd), top center
    mcx = width/2; mcy = height*0.14; sc = width/900.0
    poly = trail_polyline(pts, t, window=120, scale=sc)
    if len(poly) > 1:
        ca, sa = math.cos(math.radians(-hd)), math.sin(math.radians(-hd))
        rot = [(mcx + px*ca - py*sa, mcy + px*sa + py*ca) for px, py in poly]
        ds.line(rot, fill=(0, 220, 255, 150), width=lw)
        ddot = 4
        ds.ellipse((mcx-ddot, mcy-ddot, mcx+ddot, mcy+ddot), fill=(255,90,90,230))
    # corner brackets
    m = width*0.06
    for (x1, y1, x2, y2) in [(m, m, m+width*0.10, m), (m, m, m, m+height*0.05),
                             (width-m, m, width-m, m+height*0.05), (width-m, m, width-m-10, m),
                             (m, height-m, m+width*0.10, height-m), (m, height-m, m, height-m-height*0.05),
                             (width-m, height-m, width-m, height-m-height*0.05), (width-m, height-m, width-m-10, height-m)]:
        ds.line((x1, y1, x2, y2), fill=cyan, width=lw)

    glow = glow.filter(ImageFilter.GaussianBlur(width//60))
    img.alpha_composite(glow)
    img.alpha_composite(sharp)


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
    ap.add_argument("--layout", default="full", choices=["minimal","full","map","holo"])
    ap.add_argument("--pan", default=None, help="pan keyframes 't:deg,t:deg' matching OFX PAN keyframes")
    ap.add_argument("--pan-log", default=None, help="OFX render log (reframe_ofx.log) — reads pan(t) directly from the plugin")
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
    pan_spec = parse_pan(a.pan) if a.pan else (parse_pan_log(a.pan_log) if a.pan_log else None)
    render(ms, pts, start_ts, fps, frames, a.width, a.height, a.layout,
           os.path.splitext(out)[0]+"_frames", pan_spec)
    encode(os.path.splitext(out)[0]+"_frames", fps, out)
    print("OK", out, frames, "frames", fps, "fps")
    if a.timeline:
        build_timeline(a.clip, out)

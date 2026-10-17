"""cli.py — one-command pipeline: GPX + clip -> overlay MOV + Fusion payloads.

Usage:
  python -m telemetry.cli <track.gpx> <clip> [--offset 0.0] [--fps 50]
      [--codec prores|qtrle] [--out OUTDIR] [--canvas 1920x1080]
"""
import argparse
import os
import sys

from .gpx_time_slicer import slice_gpx
from .gpx_parser import parse_gpx
from .overlay_renderer import render_overlay
from .fusion_gpx_bridge import bridge


def main(argv=None):
    ap = argparse.ArgumentParser(prog="telemetry.cli")
    ap.add_argument("gpx")
    ap.add_argument("clip")
    ap.add_argument("--offset", type=float, default=0.0, help="sync drift [s]")
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--codec", choices=["prores", "qtrle"], default="prores")
    ap.add_argument("--out", default="telemetry_out")
    ap.add_argument("--canvas", default="1920x1080")
    a = ap.parse_args(argv)

    w, h = (int(x) for x in a.canvas.lower().split("x"))
    frames, meta = slice_gpx(a.gpx, a.clip, offset_s=a.offset, fps=a.fps)
    if not frames:
        print("no GPX points inside clip window (offset=%s)" % a.offset)
        return 1
    print("clip start: %s (%s), fps=%s, frames=%d" %
          (meta["start_utc"], meta["start_source"], meta["fps"], meta["frames"]))
    print("sliced: %d frames, speed %.1f..%.1f km/h, alt %.0f..%.0f m" %
          (len(frames), min(f.speed_kmh for f in frames),
           max(f.speed_kmh for f in frames),
           min(f.alt for f in frames), max(f.alt for f in frames)))

    os.makedirs(a.out, exist_ok=True)
    pts = [(f.lat, f.lon) for f in frames]
    mov, rc = render_overlay(frames, pts, os.path.join(a.out, "overlay_%s.mov" % a.codec),
                             canvas_w=w, canvas_h=h, codec=a.codec, fps=meta["fps"])
    print("overlay: %s (ffmpeg rc=%d)" % (mov, rc))
    files = bridge(frames, meta, a.out)
    print("fusion payloads: " + ", ".join(os.path.basename(x) for x in files))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

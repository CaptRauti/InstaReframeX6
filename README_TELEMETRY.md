# GPX Telemetry Overlay Engine (`telemetry/`)

Modular Python package that pairs **continuous GPX log files** with
**intermittent action-cam clips** using absolute UTC creation timestamps.
Dual output strategy, pure stdlib + numpy + Pillow + ffmpeg.

## Directory structure

```
telemetry/
  __init__.py            package API (slice_gpx, probe_video, parse_gpx)
  metadata.py            UTC creation time + duration (ffprobe, Insta360 fallbacks)
  gpx_parser.py          stdlib GPX parser (trkpt -> time/lat/lon/ele + derived speed/bearing)
  gpx_time_slicer.py     CORE: clip-UTC slicing + frame-accurate interpolation
  overlay_renderer.py    Strategy A: transparent ProRes 4444 / QTRLE alpha overlay
  fusion_gpx_bridge.py   Strategy B: JSON + Lua payloads + Fusion keyframe template
  cli.py                 one-command pipeline
  tests/make_test_gpx.py synthetic GPX generator for end-to-end tests
```

## Quick start

```bash
python -m telemetry.cli track.gpx clip.mp4 --offset 0.0 --codec prores --out out/
# outputs: out/overlay_prores.mov (alpha), telemetry.json, telemetry_data.lua, fusion_apply.lua
```

## UTC resolution (Insta360 reality)

Split `.mp4` clips produced by `ffmpeg -c copy` **lose** `creation_time`.
Resolution order in `metadata.py`:

1. `ffprobe` `creation_time` of the clip (GoPro/phone MP4 work directly)
2. **`.insv` sidecar lookup** — strips `_lensN.mp4`, finds the original `.insv`
   in the clip's dir or parent, probes it (verified: `2026-09-18T18:55:57Z` =
   filename `20:55:57` local, UTC+2)
3. Insta360 filename pattern `VID_YYYYMMDD_HHMMSS` → local time → UTC

## Frame-accurate model

```
frame i  →  t_i = clip_start_utc + offset + i / fps        (absolute UTC)
GPX window = [clip_start + offset, clip_start + offset + duration]
```

Interpolation: linear on the time axis for speed/alt/lat/lon; **heading is
interpolated via sin/cos decomposition** so a 359°→1° transition never wraps
through 180°. Speed derived from haversine distance / Δt, bearing from
great-circle formula.

## Strategy A — transparent overlay video

PIL RGBA canvas per frame (speedometer gauge + needle, km/h + mph, altitude,
lat/lon, compass, mini track map), background `RGBA(0,0,0,0)`. Export:

- `prores_ks -profile:v 4444 -pix_fmt yuva444p10le` → verified `yuva444p12le`
  with alpha plane (ProRes 4444 stores 12-bit alpha)
- `qtrle -pix_fmt rgba` → verified `argb`

Drop the MOV on any track above the clip in Resolve — alpha composites natively.

## Strategy B — Fusion payloads

- `telemetry.json` — portable payload (fps, clip_start_utc, per-frame values)
- `telemetry_data.lua` — Lua table consumable by a Fuse (Fusion Lua has no
  json module; the table is the native format)
- `fusion_apply.lua` — template that creates `Text+` / `Transform` nodes and
  keyframes them (`fu:KEYFRAME(t, value)`) — **needs one live test in Resolve 21**
  (keyframe API is the one part validated only in-app)

## Verified end-to-end (2026-10-18)

Real X6 clip `VID_20260918_205557_00_014_lens1.mp4` (2.5 s, 50 fps, 125 frames,
no creation_time): sidecar `.insv` found → start `2026-09-18T18:55:57+00:00`,
sliced 125 frames, speed 0→67 km/h, alt 110→123 m, ProRes + QTRLE rc=0,
frame PNG corners `RGBA(0,0,0,0)`, `--offset 0.5` correctly shifts the window.

## Limitations & next steps

- Fusion keyframe injection via `fu:KEYFRAME` is written pcall-robust but
  untested in-app (Resolve 21 script sandbox limits).
- GPX speed is derived from positions (10 Hz sampling); a native speed
  extension parser (e.g. Garmin `gpx:speed`) is a small addition.
- Track map is normalized per clip window; global map support = later.

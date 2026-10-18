# InstaReframeX6 OFX Plugin — Usage Guide (EN)

Native OpenFX effect for DaVinci Resolve: reframes Insta360 X6 dual-fisheye clips
into a rectilinear, upright view directly on the Edit page — no pre-split, no Fusion graph.

## Install (Windows)

1. Copy the bundle to the OFX scan path:
   `C:\Program Files\Common Files\OFX\Plugins\InstaReframeX6.ofx.bundle`
   (layout: `Contents\Info.plist` + `Contents\Win64\InstaReframeX6.ofx`)
2. Restart DaVinci Resolve. The plugin appears under Effects → **InstaReframeX6**.

## Build from source

- Requirements: llvm-mingw (clang), OpenFX SDK (https://github.com/AcademySoftwareFoundation/openfx)
- `bash ofx/build.sh` — compiles the OFX support library, `plugin_v1.cpp`, links `InstaReframeX6_v1.dll`
- Install: copy `InstaReframeX6_v1.dll` to `.../InstaReframeX6.ofx.bundle/Contents/Win64/InstaReframeX6.ofx` (needs admin once; grant ACL for later swaps)

## Step by step (EN)

1. Import the **combined** X6 clip (front = left half, back = right half) into the Media Pool.
2. Put it on a 16:9 timeline (e.g. 3840×2160). Resolve scales the clip to timeline resolution; the plugin adapts calibration automatically.
3. Edit page → Effects panel → group **InstaReframeX6** → drag **InstaReframeX6 Reframe** onto the clip.
4. Inspector:
   - **Calibration file (.calib)** — the X6 `.calib` file for this clip (e.g. `VID_..._lens1.calib`). Empty = built-in X6 defaults.
   - **FOV** — horizontal field of view of the output view (e.g. 60–100).
   - **Pan / Tilt / Roll** — virtual camera angles. Pan 0 = front lens, Pan 180 = back lens.
   - **Seam yaw / Seam pitch** — fine-tuning of the back lens orientation (only affects back-facing views).
5. Play / render. Export works; playback at 4K is CPU-bound (~260 ms/frame), a GPU kernel is planned.

## Step by step (DE)

1. Den **kombinierten** X6-Clip (Front = linke Hälfte, Back = rechte Hälfte) ins Media-Panel importieren.
2. Auf eine 16:9-Timeline legen (z. B. 3840×2160). Resolve skaliert den Clip auf die Timeline-Auflösung; das Plugin passt die Kalibrierung automatisch an.
3. Edit-Page → Effekte-Panel → Gruppe **InstaReframeX6** → **InstaReframeX6 Reframe** auf den Clip ziehen.
4. Inspector:
   - **Calibration file (.calib)** — die `.calib`-Datei des Clips (z. B. `VID_..._lens1.calib`). Leer = X6-Standardkalibrierung.
   - **FOV** — Bildwinkel der Ausgabe (z. B. 60–100).
   - **Pan / Tilt / Roll** — virtuelle Kamerawinkel. Pan 0 = Front-Linse, Pan 180 = Back-Linse.
   - **Seam yaw / Seam pitch** — Feinabgleich der Back-Linse (wirkt nur auf zurückgerichtete Blicke).
5. Abspielen / rendern. Export funktioniert; 4K-Playback ist CPU-begrenzt (~260 ms/Frame), GPU-Kernel geplant.

## Verified end-to-end (Resolve 21.1, X6 clip)

- Parameters reach the render (FOV, Pan, Tilt, Roll, Seam, Calib path logged in render log)
- `.calib` file loads and drives the MEI warp
- Front view (Pan 0) and back view (Pan 180): full-frame, rectilinear, upright, no mirroring
- Seam yaw shifts the back view measurably (~37 px at 10°)
- Multi-frame playback: correct frame rendering at all timecodes

# InstaReframeX6 — Step-by-Step Guide (English)

This guide walks you through the complete workflow: from an Insta360 X6
`.insv` recording to a finished ReFrame in the DaVinci Resolve Fusion page.

---

## 1. What you need

| Requirement | Notes |
|---|---|
| DaVinci Resolve **Studio 21.x** | The Fusion page is required (included in Studio) |
| Insta360 X6 `.insv` files | Your 360° recordings from the camera |
| ffmpeg | Only for Path A (the import script). Auto-detected or set in `scripts/import_insv.lua` |
| Python 3 | Only if you want to generate the `.calib` calibration manually |

---

## 2. Install the plugin

1. Copy `Fuses/InstaReframeX6.fuse` to **one** of these folders:
   - `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Fuses\`
   - or `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Fuses\`
2. Restart DaVinci Resolve.
3. Check: On the Fusion page, open the Effects Library and look in
   `Fuses\Insta360` — the tool shows as **X6R**. You can also type
   **Shift+Space** and search for "InstaReframeX6".

---

## 3. Path A — Fully automatic (recommended)

The import script does everything: split, calibration, import, timeline.

1. **Run the script**: In Resolve, go to
   `Workspace → Scripts → insta360 → import_insv.lua`.
   (If the menu doesn't show it, use `Workspace → Scripts → Reload and run…`
   and select the file manually.)
2. **Select your `.insv` file** in the file dialog.
3. The script now:
   - splits the `.insv` losslessly into `_lens0.mp4` (back) and
     `_lens1.mp4` (front) — both in `<folder>\insta_reframe\`
   - generates `lens1.calib` (the lens calibration) next to the front clip
   - imports both clips into the Media Pool
   - appends them to the timeline: **V1 = lens0 (Back), V2 = lens1 (Front)**
4. You should see a message like `Importiert: 2` / `Timeline: true`.

### 3.1 Wire the Fuse in the Fusion page

1. Put the playhead on the V2 clip (Front) and go to the **Fusion page**
   (button in the top toolbar, or `Shift+6`).
2. The clip comp opens. You will see a `MediaIn1` node already connected to
   a `MediaOut1`.
3. **Add the back stream**: In the Media Pool (left panel), find the
   `_lens0.mp4` clip (bin "Master"), and **drag it with the mouse into the
   node graph**. A new `MediaIn2` node appears — this is the only way in
   Resolve 21 (setting it via script is blocked by Resolve).
4. **Add the Fuse**: Press **Shift+Space**, type `InstaReframeX6`, press
   Enter. A node with the **X6R** icon appears.
5. **Wire the nodes** (drag from the green output to the input):
   ```
   MediaIn1 (lens1/Front) → Fuse "Front"
   MediaIn2 (lens0/Back)  → Fuse "Back"
   Fuse Output            → MediaOut1 "Input"
   ```

> 💡 **Tip**: If you click the Fuse node, the Inspector on the right shows
> the parameters. If you do not see the Front/Back inputs, click **Reload**
> in the Inspector.

### 3.2 Adjust the image

1. Select the Fuse node.
2. In the **Inspector** set:
   - **Aspect Ratio**: e.g. `4K UHD` for 16:9, `9:16` for Reels/TikTok
   - **FOV**: your desired field of view (start with 60–80)
3. **Look around** with the sliders **Pan / Tilt / Roll**, or drag the
   **Aim crosshair** directly in the viewer.

### 3.3 Stitching line correction (seam fine-tuning)

If you see a small offset at the stitching line (front/back transition):

1. Turn the view so the seam is clearly visible in the viewer.
2. Slowly move **BackYaw** (horizontal) until the wall/edge runs through
   continuously across the seam.
3. If a vertical offset remains, add **BackPitch**.
4. Typical values are between −1° and +1°.

---

## 4. Path B — Manual workflow

If you prefer to prepare the streams yourself:

1. **Split the `.insv`** (lossless, no quality loss):
   ```bash
   ffmpeg -i VID_xxxx.insv -map 0:0 -c copy lens0.mp4
   ffmpeg -i VID_xxxx.insv -map 0:1 -c copy lens1.mp4
   ```
   (Windows: double-click `scripts/split_insv.bat` after putting an `.insv`
   into the same folder, or run it from the command line.)
2. **Generate calibration** (optional but recommended):
   ```bash
   python tools/insv_calib.py VID_xxxx.insv -o lens1.calib
   ```
   → creates `lens1.calib` next to the front clip. The Fuse finds it
   automatically at render time.
3. In the Edit page place lens1 (front) on **V2** and lens0 (back) on **V1**.
4. Continue at step **3.1** (wire the Fuse) above — same procedure.

---

## 5. Rendering in 4K

1. On the **Deliver page** choose your format (e.g. MP4/H.265, 3840×2160,
   or 1080×1920 for 9:16).
2. If you chose Aspect=Custom in the Fuse, set OutWidth/OutHeight there.
3. Add to Render Queue and render.

> ⚠️ **Note**: In a clip comp, the timeline/composition format also affects
> the display. If the output looks cropped, check the project settings
> (timeline resolution) match your aspect preset.

---

## 6. Troubleshooting

| Problem | Solution |
|---|---|
| Tool not found in Effects Library | Restart Resolve; check the Fuse folder path (see step 2) |
| Viewer shows black | Check `Front` and `Back` are connected to the media inputs; click **Reload** on the Fuse |
| Back doesn't load via script | The second stream can only be added by **drag & drop** from the Media Pool in Resolve 21 |
| Calibration not loaded | Make sure `lens1.calib` is in the same folder as the front clip; the Fuse reads it automatically |
| Seam offset at close objects (< ~3 m) | This is physical parallax (two lenses see from slightly different positions). Reduce with BackYaw/BackPitch; insta360 Studio uses an unreproducible AI model for this |
| Slider changes have no effect | Click **Reload** in the Inspector, then move the slider again |

---

*Feedback, issues and feature requests: please open a GitHub issue or fork
the repository.*
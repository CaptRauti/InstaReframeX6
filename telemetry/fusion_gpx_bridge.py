"""fusion_gpx_bridge.py — Strategy B: GPX data for DaVinci Resolve Fusion.

Emits the sliced track as:
  1. telemetry.json  — portable payload (clip meta + per-frame values)
  2. telemetry_data.lua — Lua table consumable by a Fuse/macro in Resolve
     (Fusion Lua has no json module; a Lua table is the native format)
  3. fusion_apply.lua — template that creates Text+/Transform nodes and
     keyframes them from the table (run inside Resolve's script console).

Keyframe API used: fu:KEYFRAME() + node:SetInput(...) — pcall-robust,
documented to be live-tested in Resolve 21 (keyframe API is the one part
that must be validated in the app).
"""
import json
import os


def _lua_num(v):
    return "%.6f" % float(v)


def export_json(frames, meta, out_path):
    payload = {
        "fps": meta["fps"],
        "clip_start_utc": meta["start_utc"],
        "start_source": meta["start_source"],
        "offset_s": meta["offset_s"],
        "duration_ms": meta["duration_ms"],
        "frames": [
            {"frame": fr.frame, "t": fr.t_rel, "speed_kmh": round(fr.speed_kmh, 3),
             "speed_mph": round(fr.speed_mph, 3), "alt": round(fr.alt, 2),
             "heading": round(fr.heading, 2), "lat": fr.lat, "lon": fr.lon}
            for fr in frames
        ],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)
    return out_path


def export_lua(frames, meta, out_path):
    """Lua table payload: telemetry_data.lua returns the table."""
    lines = ["-- InstaReframeX6 telemetry payload (generated, UTC-anchored)",
             "return {",
             "  fps = %s," % _lua_num(meta["fps"]),
             "  clip_start_utc = \"%s\"," % meta["start_utc"],
             "  offset_s = %s," % _lua_num(meta["offset_s"]),
             "  frames = {"]
    for fr in frames:
        lines.append("    [%d] = { t=%s, speed_kmh=%s, speed_mph=%s, alt=%s, "
                     "heading=%s, lat=%s, lon=%s }," % (
                     fr.frame, _lua_num(fr.t_rel), _lua_num(fr.speed_kmh),
                     _lua_num(fr.speed_mph), _lua_num(fr.alt),
                     _lua_num(fr.heading), _lua_num(fr.lat), _lua_num(fr.lon)))
    lines.append("  }")
    lines.append("}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


FUSION_APPLY_TEMPLATE = r'''-- fusion_apply.lua — keyframe Text+ / Transform from telemetry_data.lua
-- Run in Resolve: Workspace > Scripts (Fusion page with a comp open).
local data = dofile("C:/path/to/telemetry_data.lua")

local comp = fusion.CurrentComp
if not comp then print("open a comp first"); return end

-- Text+ node: speed readout
local okT, txt = pcall(function() return comp:AddTool("TextPlus", "SpeedText") end)
if okT and txt then
    for i, f in ipairs(data.frames) do
        local okK, kf = pcall(function()
            txt:SetInput("TextBmd", fu:KEYFRAME(f.t, tostring(math.floor(f.speed_kmh)) .. " km/h"))
        end)
        if not okK then print("keyframe API rejected SetInput: " .. tostring(kf)); break end
    end
end

-- Transform node: needle rotation by heading (angle keyframes)
local okX, tr = pcall(function() return comp:AddTool("Transform", "Needle") end)
if okX and tr then
    for i, f in ipairs(data.frames) do
        pcall(function()
            tr:SetInput("Angle", fu:KEYFRAME(f.t, f.heading))
        end)
    end
end
print("telemetry keyframes applied: " .. tostring(#data.frames) .. " frames")
'''


def export_apply_lua(out_path, data_path):
    code = FUSION_APPLY_TEMPLATE.replace("C:/path/to/telemetry_data.lua",
                                          data_path.replace("\\", "/"))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(code)
    return out_path


def bridge(frames, meta, out_dir):
    jp = export_json(frames, meta, os.path.join(out_dir, "telemetry.json"))
    lp = export_lua(frames, meta, os.path.join(out_dir, "telemetry_data.lua"))
    ap = export_apply_lua(os.path.join(out_dir, "fusion_apply.lua"), lp)
    return [jp, lp, ap]

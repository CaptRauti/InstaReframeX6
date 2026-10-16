-- import_insv.lua — Insta360 X6: .insv direkt in Resolve importieren (v2.0)
--
-- Ein Skript für Resolve: Es splittet eine .insv verlustfrei (ffmpeg -c copy)
-- in lens0.mp4/lens1.mp4, erzeugt die Kalibrierungsdatei (insv_calib.py)
-- und importiert beide Clips in den Media Pool — auf Wunsch auf V2/V1.
--
-- Ausführen: Resolve > Workspace > Scripts > import_insv.lua  (bzw. über
-- das Skript-Panel). Das Skript fragt nach der .insv-Datei.
--
-- Voraussetzungen:
--   * ffmpeg im PATH (oder FFMPEG_BIN unten anpassen)
--   * tools/insv_calib.py im Skript-Ordner (dieses Skript findet es selbst)
--   * Python 3 im PATH (für insv_calib.py)

local FFMPEG = "ffmpeg"
local PYTHON = "python"

local function log(m)
    print("[insta-import] " .. m)
end

-- --- Datei-Dialog (Fusion UI, falls verfügbar) ---
local function pick_insv()
    local dlg = fusion:GetDisplayUI()
    if dlg and dlg.FileDialog then
        local path = dlg:FileDialog("Open", "Insta360 X6 .insv wählen", "", "*.insv")
        if path and path ~= "" then return path end
    end
    return nil
end

-- --- Pfad-Helfer ---
local function split_path(p)
    local dir, file = p:match("^(.*)[/\\]([^/\\]+)$")
    if not dir then dir, file = ".", p end
    local base = file:match("^(.*)%.[^%.]+$") or file
    return dir, file, base
end

local function file_exists(p)
    local f = io.open(p, "r")
    if f then f:close() return true end
    return false
end

-- --- ffmpeg-Split (verlustfrei) ---
local function split_streams(insv, outdir, base)
    local out0 = outdir .. "/" .. base .. "_lens0.mp4"
    local out1 = outdir .. "/" .. base .. "_lens1.mp4"
    local r0 = os.execute(string.format('"%s" -y -i "%s" -map 0:0 -c copy "%s" 2>nul',
                                        FFMPEG, insv, out0))
    if r0 ~= 0 or not file_exists(out0) then
        return nil, "ffmpeg Stream 0 fehlgeschlagen"
    end
    local r1 = os.execute(string.format('"%s" -y -i "%s" -map 0:1 -c copy "%s" 2>nul',
                                        FFMPEG, insv, out1))
    if r1 ~= 0 or not file_exists(out1) then
        return nil, "ffmpeg Stream 1 fehlgeschlagen"
    end
    return out0, out1
end

-- --- Kalibrierung erzeugen (neben dem Front-Clip lens1) ---
local function make_calib(insv, lens1)
    local calib = lens1:gsub("%.[^%.]+$", "") .. ".calib"
    -- Skript liegt in scripts/, insv_calib.py in tools/ -> ../tools/insv_calib.py
    local scriptdir = debug.getinfo(1, "S").source:match("^@(.*)[/\\][^/\\]+$")
    local candidates = {
        (scriptdir or ".") .. "/../tools/insv_calib.py",
        (scriptdir or ".") .. "/insv_calib.py",
        (scriptdir or ".") .. "/tools/insv_calib.py",
    }
    local calib_py
    for _, c in ipairs(candidates) do
        local f = io.open(c, "r")
        if f then f:close() calib_py = c break end
    end
    if not calib_py then
        log("WARN: insv_calib.py nicht gefunden — Auto-Kalibrierung übersprungen")
        return false
    end
    local cmd = string.format('"%s" "%s" "%s" -o "%s"', PYTHON, calib_py, insv, calib)
    local ok = os.execute(cmd)
    log("Kalibrierung: " .. tostring(ok == 0 or ok == true) .. " -> " .. calib)
    return true
end

-- --- Media-Pool-Import + Timeline ---
local function import_to_pool(paths, to_timeline)
    local mp = resolve:GetMediaPool()
    if not mp then log("kein MediaPool"); return false end
    local items = mp:ImportMedia(paths)
    if not items or #items == 0 then
        log("Import fehlgeschlagen (keine Items)")
        return false
    end
    log("Importiert: " .. tostring(#items) .. " Clip(s)")
    if not to_timeline then return true end

    local proj = resolve:GetProjectManager():GetCurrentProject()
    local tl = proj:GetCurrentTimeline()
    if not tl then log("keine Timeline — nur importiert"); return true end
    local ok0 = tl:AppendToTimeline({ { mediaPoolItem = items[1], trackIndex = 1 } })
    local ok1 = tl:AppendToTimeline({ { mediaPoolItem = items[2], trackIndex = 2 } })
    log("Timeline: V1(lens0)=" .. tostring(ok0) .. " V2(lens1)=" .. tostring(ok1))
    return true
end

-- --- Hauptablauf ---
local function main()
    local insv = pick_insv()
    if not insv then
        log("abgebrochen (keine Datei gewählt)")
        return
    end
    local dir, file, base = split_path(insv)
    log("Verarbeite: " .. file)

    local outdir = dir .. "/insta_reframe"
    os.execute('mkdir "' .. outdir .. '" 2>nul')

    local out0, out1 = split_streams(insv, outdir, base)
    if not out0 then
        log("FEHLER: " .. tostring(out1))
        return
    end
    log("Split OK: " .. out0)
    log("          " .. out1)

    make_calib(insv, out1)

    local ok = import_to_pool({ out0, out1 }, true)
    if ok then
        log("Fertig. lens0 (Back) auf V1, lens1 (Front) auf V2. Viel Spaß!")
    end
end

main()
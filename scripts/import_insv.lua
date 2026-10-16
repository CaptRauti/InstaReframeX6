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
-- Fallbacks fuer Umgebungen, in denen ffmpeg nicht im PATH liegt (z.B.
-- Resolve-Prozess): zuerst bekannte Installationsorte durchsuchen.
local function find_bin(name, candidates)
    local f = io.open(name, "r")
    if f then f:close() return name end
    for _, c in ipairs(candidates or {}) do
        local f2 = io.open(c, "r")
        if f2 then f2:close() return c end
    end
    -- PATH durchsuchen (Windows-Style)
    local path = os.getenv("PATH") or ""
    for p in path:gmatch("[^;]+") do
        local cand = p:gsub("\\$", "") .. "\\" .. name .. ".exe"
        local f3 = io.open(cand, "r")
        if f3 then f3:close() return cand end
    end
    return name
end

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

-- --- ffmpeg-Split (verlustfrei) — UEBER BATCH-DATEI ---
-- WICHTIG (Resolve-Lua): os.execute mit direkten, verschachtelten
-- Anfuehrungszeichen in Argumenten scheitert in Resolve (nil, 0.1s).
-- Eine temporaere .bat-Datei mit CRLF-Zeilenenden laeuft zuverlaessig.
-- Daher: Befehle in eine .bat schreiben und diese ausfuehren.
local function write_bat(path, lines)
    local fh = io.open(path, "wb")
    if not fh then return false end
    fh:write(table.concat(lines, "\r\n") .. "\r\n")
    fh:close()
    return true
end

local function run_bat(batpath)
    local ok, res = pcall(function()
        return os.execute('"' .. batpath .. '"')
    end)
    return ok and (res == true or res == 0)
end

local function split_streams(insv, outdir, base)
    local out0 = outdir .. "\\" .. base .. "_lens0.mp4"
    local out1 = outdir .. "\\" .. base .. "_lens1.mp4"
    local bat = outdir .. "\\_split.bat"
    local ok = write_bat(bat, {
        "@echo off",
        string.format('"%s" -y -hide_banner -i "%s" -map 0:0 -c copy "%s" 1>NUL 2>NUL',
                      FFMPEG, insv, out0),
        string.format('echo RC0=%%ERRORLEVEL%% >> "%s\\_rc.txt"', outdir),
        string.format('"%s" -y -hide_banner -i "%s" -map 0:1 -c copy "%s" 1>NUL 2>NUL',
                      FFMPEG, insv, out1),
        string.format('echo RC1=%%ERRORLEVEL%% >> "%s\\_rc.txt"', outdir),
    })
    if not ok then return nil, "Batch schreiben fehlgeschlagen" end
    os.execute('del "' .. outdir .. '\\_rc.txt" 2>NUL')
    if not run_bat(bat) then
        return nil, "Batch-Ausfuehrung fehlgeschlagen"
    end
    -- Ergebnisse pruefen
    local rc0, rc1 = nil, nil
    local rcF = io.open(outdir .. "\\_rc.txt", "r")
    if rcF then
        for line in rcF:lines() do
            local t = line:gsub("%s+$", "")
            local k, v = t:match("^(RC%d+)=(%d+)$")
            if k == "RC0" then rc0 = tonumber(v) end
            if k == "RC1" then rc1 = tonumber(v) end
        end
        rcF:close()
    end
    if (rc0 or 0) ~= 0 or not file_exists(out0) then
        return nil, "ffmpeg Stream 0 fehlgeschlagen (rc=" .. tostring(rc0) .. ")"
    end
    if (rc1 or 0) ~= 0 or not file_exists(out1) then
        return nil, "ffmpeg Stream 1 fehlgeschlagen (rc=" .. tostring(rc1) .. ")"
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
        -- Fallback: bekannter Installationsort (Release-Ordner)
        local rb = "C:\\Users\\stefa\\insta-reframe-x6-release\\tools\\insv_calib.py"
        local f = io.open(rb, "r")
        if f then f:close() calib_py = rb end
    end
    if not calib_py then
        log("WARN: insv_calib.py nicht gefunden — Auto-Kalibrierung übersprungen")
        return false
    end
    -- Python-Aufruf ebenfalls ueber Batch (verschachtelte Quotes meiden)
    local outdir = lens1:match("^(.*)[/\\][^/\\]+$") or "."
    local bat = outdir .. "\\_calib.bat"
    local fh = io.open(bat, "wb")
    if not fh then return false end
    fh:write(string.format('@echo off\r\n"%s" "%s" "%s" -o "%s"\r\necho RC=%%ERRORLEVEL%% >> "%s\\_rc.txt"\r\n',
                           PYTHON, calib_py, insv, calib, outdir))
    fh:close()
    os.execute('del "' .. outdir .. '\\_rc.txt" 2>NUL')
    local ok, res = pcall(function() return os.execute('"' .. bat .. '"') end)
    local rc = nil
    local rcF = io.open(outdir .. "\\_rc.txt", "r")
    if rcF then
        for line in rcF:lines() do
            local t = line:gsub("%s+$", "")
            local v = t:match("^RC=(%d+)$")
            if v then rc = tonumber(v) end
        end
        rcF:close()
    end
    local okc = (ok and (res == true or res == 0)) and rc == 0
    log("Kalibrierung: " .. tostring(okc) .. " -> " .. calib)
    return okc
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

    -- Timeline-Append ueber den MediaPool (tl:AppendToTimeline existiert in
    -- einigen Resolve-Versionen nicht — mp:AppendToTimeline ist stabil).
    local okA, res = pcall(function()
        return mp:AppendToTimeline({
            { mediaPoolItem = items[1], trackIndex = 1 },
            { mediaPoolItem = items[2], trackIndex = 2 },
        })
    end)
    if not okA then
        -- Fallback: ohne trackIndex (aktuelle Spur)
        okA, res = pcall(function()
            return mp:AppendToTimeline({ { mediaPoolItem = items[1] }, { mediaPoolItem = items[2] } })
        end)
    end
    log("Timeline: V1(lens0)=" .. tostring(okA and res ~= nil) .. " (via MediaPool)")
    return okA
end

-- --- Hauptablauf ---
local function main()
    local insv = pick_insv()
    if not insv then
        log("abgebrochen (keine Datei gewählt)")
        return
    end
    -- ffmpeg/python auflösen (PATH oder bekannte Orte)
    FFMPEG = find_bin("ffmpeg", {
        "C:\\Users\\stefa\\AppData\\Local\\hermes\\tools\\ffmpeg-9.0.1-win32-x64\\bin\\ffmpeg.exe",
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
    })
    log("ffmpeg: " .. FFMPEG)
    local dir, file, base = split_path(insv)
    log("Verarbeite: " .. file)

    local outdir = dir .. "\\insta_reframe"
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
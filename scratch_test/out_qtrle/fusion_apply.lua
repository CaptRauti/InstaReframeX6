-- fusion_apply.lua — keyframe Text+ / Transform from telemetry_data.lua
-- Run in Resolve: Workspace > Scripts (Fusion page with a comp open).
local data = dofile("scratch_test/out_qtrle/telemetry_data.lua")

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

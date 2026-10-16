# InstaReframeX6 — 360°-Reframe für Insta360 X6 in DaVinci Resolve

Reframe dein Insta360-X6-360°-Material direkt in der Fusion-Seite von DaVinci
Resolve — ohne Insta360 Studio, ohne Zwischenrender. Das Plugin nutzt die
**echte Linsenkalibrierung aus deiner `.insv`-Datei** (MEI-Modell, xi-Kalibrierung,
13 Distorsionskoeffizienten pro Linse) statt der groben generischen
v360-Näherung. Ergebnis: saubere, zusammenhängende Welt ohne
Perspektivbrüche an der Linsennaht.

## Features (v2.0)

- **360°-Reframe aus beiden Fisheye-Streams** direkt in Fusion
  (FOV / Pan / Tilt / Roll als Slider)
- **🖱️ Drag-Steuerung im Viewer**: Der „Aim"-Punkt (Fadenkreuz) wird mit der
  Maus gezogen — Pan/Tilt folgen intuitiv, wie in Insta360 Studio
- **⚙️ Auto-Kalibrierung**: Liest die Kalibrierung automatisch aus einer
  `.calib`-Datei neben dem Front-Clip (erzeugt von `tools/insv_calib.py`).
  Ohne Datei gelten eingebaute Defaults.
- **📥 Import ohne Vorfeld-Split**: `scripts/import_insv.lua` splittet eine
  `.insv` direkt in Resolve (verlustfrei), erzeugt die Kalibrierung und
  importiert beide Clips auf V1/V2.
- **Synchronisierte Front/Back-Perspektive** — eine Welt, zwei Linsen,
  keine „zwei Welten" mehr
- **Korrekte Back-Ausrichtung** (180°-Y-Strahlrotation statt Pixel-Spiegelung)
- **4K-Output** (3840×2160 als Default) und Aspect-Presets:
  4K UHD, 16:9, 9:16 (Reels/TikTok), 1:1, 4:5, 9:21, Custom
- **Verlustfreier INSV→Streams-Workflow** via ffmpeg (`-c copy`, kein Re-Encode)

## Voraussetzungen

- DaVinci Resolve **Studio 21.x** (Fusion-Seite). MEI/Kalibrierung läuft als
  DCTL-Kernel auf der GPU.
- Insta360 X6 Material (`.insv`)
- ffmpeg (für den Split — nur falls das Import-Skript genutzt wird)
- Python 3 (nur für die Kalibrierungs-Erzeugung — optional, eingebaute
  Defaults reichen für eine Standard-X6)

## Installation

1. Kopiere `Fuses/InstaReframeX6.fuse` in einen der Fuse-Ordner:
   - `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Fuses\`
   - oder `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Fuses\`
2. Starte DaVinci Resolve neu (oder klicke im Inspector nach dem Einfügen
   auf „Neu laden").
3. In der Fusion-Seite findest du das Tool unter dem Symbol **X6R** in der
   Kategorie `Fuses\Insta360`, oder über **Shift+Space** („InstaReframeX6").

## Anwendung

### Weg A — Import-Skript (empfohlen, kein Vorfeld-Split)
1. `scripts/import_insv.lua` in Resolve ausführen (Workspace → Scripts).
2. `.insv`-Datei wählen → das Skript splittet in
   `<ordner>\insta_reframe\<name>_lens0.mp4` / `_lens1.mp4`, erzeugt die
   `.calib` daneben und importiert beide Clips auf V1 (Back) / V2 (Front).
3. Auf V2 die Fusion-Comp öffnen, den Back-Clip als zusätzliche MediaIn in
   den Graph ziehen (Drag&Drop), Fuse per Shift+Space einfügen und verdrahten.

### Weg B — manuell (Streams vorbereitet)
1. **Streams extrahieren** (einmalig, verlustfrei):
   ```bash
   ffmpeg -i VID_xxxx.insv -map 0:0 -c copy lens0.mp4
   ffmpeg -i VID_xxxx.insv -map 0:1 -c copy lens1.mp4
   ```
   (Fertige Skripte: `scripts/split_insv.bat`; für Auto-Kalibrierung zusätzlich
   `python tools/insv_calib.py VID_xxxx.insv` → erzeugt `lens1.calib` neben dem
   Front-Clip.)
2. **Timeline**: Beide Clips auf V2 (Stream 1 = **Front**) und V1
   (Stream 0 = **Back**) legen.
3. **Fusion-Comp** auf dem Front-Clip öffnen. Der Back-Clip muss als
   zusätzliche MediaIn in den Graph (Drag&Drop).
4. **Verdrahten**: `Front` ← MediaIn(lens1), `Back` ← MediaIn(lens0),
   MediaOut ← Fuse-Output.
5. **Inspector**: FOV, Roll einstellen; Aspect-Preset wählen. Pan/Tilt per
   **Aim-Fadenkreuz im Viewer ziehen** (oder Slider).

## Parameter

| Param | Default | Bedeutung |
|---|---|---|
| FOV | 60 | Vertikales Sichtfeld in Grad (15–170) |
| Aim | Mittelpunkt | **Blickrichtung im Viewer ziehen** (Maus): X→Pan, Y→Tilt |
| Pan (Yaw) | 0 | Horizontale Drehung (−180…180), optionaler Slider |
| Tilt (Pitch) | 0 | Vertikale Drehung (−90…90), optionaler Slider |
| Roll | 0 | Rotation um die Blickachse (−180…180) |
| Aspect | 4K UHD | Ausgabeformat-Preset (4K/16:9/9:16/1:1/4:5/9:21/Custom) |
| OutWidth/OutHeight | 1920×1080 | Manuelle Größe (nur bei Aspect=Custom) |

## Auto-Kalibrierung (⚙️)

Der Fuse sucht beim Rendern automatisch eine `.calib`-Datei **neben dem
Front-Clip** (gleicher Basisname, z.B. `lens1.mp4` → `lens1.calib`). Die
Datei wird erzeugt mit:

```bash
python tools/insv_calib.py VID_xxxx.insv -o lens1.calib
```

Format: einfache `Key=Value`-Zeilen (`front_xi=2.45543`, `front_m0=0.999973`,
…). Liegt keine Datei vor, gelten die eingebauten Defaults (verifizierte
X6-Werte, Firmware v1.1.78).

## Wie funktioniert das Mapping?

Pro Output-Pixel wird ein Sichtstrahl berechnet, mit Pan/Tilt/Roll rotiert und
durch die **MEI-Projektion** der jeweiligen Linse geworfen:

```
Ray → Roll/Tilt/Pan → Extrinsik (je Linse, aus .calib) → MEI-Forward → Distorsion → Sample → Output
```

Die Linsenkalibrierung (xi=2.45543, fx≈3611, cx/cy, k1–k4, p1/p2, s1–s4 je
Linse) stammt aus den `.insv`-Metadaten (INFO f111/f112). Die Back-Linse wird
über eine echte 180°-Y-Rotation der Strahlen abgebildet — die Rückansicht ist
daher korrekt (nicht spiegelverkehrt). Die Sensor-Roll (~89,66°) wird bewusst
NICHT angewendet (verifiziert: verschlechtert das Ergebnis).

## Bekannte Grenzen

- **Naht-/Parallax-Artefakte bei sehr nahen Objekten (< ~3 m)**: Insta360
  löst das mit einem trainierten KI-Modell (nicht reproduzierbar).
- Die Kalibrierung kann pro Aufnahme geladen werden (Auto-.calib); ohne
  Datei gelten die verifizierten X6-Standardwerte.
- In Clip-Comps bestimmt das Comp-Format die Anzeige — Aspect-Presets liefern
  die Bildgröße, das Projektformat muss separat passend gewählt werden.

## Lizenz

MIT. Siehe [LICENSE](LICENSE).

Dank an Benjamin Henriksson ([insv-stitch](https://github.com/BenjaminHenriksson/insv-stitch))
für die verifizierte MEI-Pipeline als Referenz.

---

*Entwickelt für die eigene X6-Workflow in DaVinci Resolve — gern Forks &
Verbesserungen!*
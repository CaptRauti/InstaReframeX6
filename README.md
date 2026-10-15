# InstaReframeX6 — 360°-Reframe für Insta360 X6 in DaVinci Resolve

Reframe dein Insta360-X6-360°-Material direkt in der Fusion-Seite von DaVinci
Resolve — ohne Insta360 Studio, ohne Zwischenrender. Das Plugin nutzt die
**echte Linsenkalibrierung aus deiner `.insv`-Datei** (MEI-Modell, xi-Kalibrierung,
13 Distorsionskoeffizienten pro Linse) statt der groben generischen
v360-Näherung. Ergebnis: saubere, zusammenhängende Welt ohne
Perspektivbrüche an der Linsennaht.

## Features

- **360°-Reframe aus beiden Fisheye-Streams** direkt in Fusion
  (FOV / Pan / Tilt / Roll als Slider)
- **Synchronisierte Front/Back-Perspektive** — eine Welt, zwei Linsen,
  keine „zwei Welten" mehr
- **Korrekte Back-Ausrichtung** (180°-Y-Strahlrotation statt Pixel-Spiegelung)
- **4K-Output** (3840×2160 als Default) und weitere Aspect-Presets:
  4K UHD, 16:9, 9:16 (Reels/TikTok), 1:1, 4:5, 9:21, Custom
- **Verlustfreier INSV→Streams-Workflow** via ffmpeg (`-c copy`, kein Re-Encode)
- **Kalibrierung im Plugin eingebaut** — die Werte wurden aus einer echten
  X6-`.insv` (Firmware v1.1.78) extrahiert

## Voraussetzungen

- DaVinci Resolve **Studio 21.x** (Fusion-Seite). Die MEI/Kalibrierung läuft als
  DCTL-Kernel auf der GPU.
- Insta360 X6 Material (`.insv`), als zwei Streams vorbereitet (siehe unten)
- ffmpeg (für den Stream-Split; einmalig)

## Installation

1. Kopiere `Fuses/InstaReframeX6.fuse` in einen der Fuse-Ordner:
   - `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Fuses\`
   - oder `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Fuses\`
2. Starte DaVinci Resolve neu.
3. In der Fusion-Seite findest du das Tool unter dem Symbol **X6R** in der
   Kategorie `Fuses\Insta360`, oder über **Shift+Space** („InstaReframeX6").

## Anwendung

1. **Streams extrahieren** (einmalig, verlustfrei):
   ```bash
   ffmpeg -i VID_xxxx.insv -map 0:0 -c copy lens0.mp4
   ffmpeg -i VID_xxxx.insv -map 0:1 -c copy lens1.mp4
   ```
   (Fertige Skripte: `scripts/split_insv.bat`)
2. **Timeline**: Beide Clips auf V2 (Stream 1 = **Front**) und V1
   (Stream 0 = **Back**) legen.
3. **Fusion-Comp** auf dem Front-Clip öffnen. Der zweite Clip (Back) muss als
   zusätzliche MediaIn in den Graph gezogen werden (Drag&Drop aus der Mediathek).
4. **Verdrahten**:
   - `Front` ← MediaIn (Stream 1 / lens1.mp4)
   - `Back`  ← MediaIn (Stream 0 / lens0.mp4)
   - MediaOut ← Fuse-Output
5. **Inspector**: FOV, Pan, Tilt, Roll einstellen; Aspect-Preset wählen.
   Das Fuse-Output liefert das Bild in der Preset-Größe (z.B. 1080×1920 für 9:16).
6. Damit der **Viewer** die Ausgabegröße zeigt, muss das Comp-Format passen
   (Fusion → Einstellungen → Format bzw. das Projektformat auf das gewünschte
   Seitenverhältnis stellen).

## Parameter

| Param | Default | Bedeutung |
|---|---|---|
| FOV | 60 | Vertikales Sichtfeld in Grad (15–170) |
| Pan (Yaw) | 0 | Horizontale Drehung (−180…180) |
| Tilt (Pitch) | 0 | Vertikale Drehung (−90…90) |
| Roll | 0 | Rotation um die Blickachse (−180…180) |
| Aspect | 4K UHD | Ausgabeformat-Preset (4K/16:9/9:16/1:1/4:5/9:21/Custom) |
| OutWidth/OutHeight | 1920×1080 | Manuelle Größe (nur bei Aspect=Custom) |

## Wie funktioniert das Mapping?

Pro Output-Pixel wird ein Sichtstrahl berechnet, mit Pan/Tilt/Roll rotiert und
durch die **MEI-Projektion** (Katadioptrisches Modell) der jeweiligen Linse
geworfen:

```
Ray → Roll/Tilt/Pan → Extrinsik (je Linse) → MEI-Forward → Distorsion → Sample → Output
```

Die Linsenkalibrierung (xi=2.45543, fx≈3611, cx/cy, k1–k4, p1/p2, s1–s4 je
Linse) stammt aus den `.insv`-Metadaten (INFO f111/f112) und ist im Kernel
eingebaut. Die Back-Linse wird über eine echte 180°-Y-Rotation der Strahlen
abgebildet — daher ist die Rückansicht korrekt (nicht spiegelverkehrt).

Die Sensor-Roll (~89,66°) wird bewusst NICHT angewendet (verifiziert:
verschlechtert das Ergebnis).

## Bekannte Grenzen

- **Naht-/Parallax-Artefakte bei sehr nahen Objekten (< ~3 m)**: Insta360
  löst das mit einem trainierten KI-Modell (nicht reproduzierbar). Für
  normale Aufnahmedistanzen ist die Naht sauber.
- Die Kalibrierung ist fest eingebaut (Stand: eine X6, Firmware v1.1.78).
  Zwischen X6-Exemplaren sind die Werte praktisch identisch; bei Messwerten
  außerhalb der Norm kann man die Konstanten im Kernel ersetzen.
- In Clip-Comps bestimmt das Comp-Format die Anzeige — Aspect-Presets liefern
  die Bildgröße, das Projektformat muss separat passend gewählt werden.

## Lizenz

MIT. Siehe [LICENSE](LICENSE).

Dank an Benjamin Henriksson ([insv-stitch](https://github.com/BenjaminHenriksson/insv-stitch))
für die verifizierte MEI-Pipeline als Referenz.

---

*Entwickelt für die eigene X6-Workflow in DaVinci Resolve — gern Forks &
Verbesserungen!*
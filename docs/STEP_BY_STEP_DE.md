# InstaReframeX6 — Schritt-für-Schritt-Anleitung (Deutsch)

Diese Anleitung führt dich durch den kompletten Workflow: von einer
Insta360-X6-`.insv`-Aufnahme bis zum fertigen ReFrame in der Fusion-Seite
von DaVinci Resolve.

---

## 1. Was du brauchst

| Voraussetzung | Hinweise |
|---|---|
| DaVinci Resolve **Studio 21.x** | Die Fusion-Seite ist erforderlich (im Studio enthalten) |
| Insta360-X6-`.insv`-Dateien | Deine 360°-Aufnahmen von der Kamera |
| ffmpeg | Nur für Weg A (Import-Skript). Wird automatisch gefunden oder in `scripts/import_insv.lua` gesetzt |
| Python 3 | Nur nötig, wenn du die `.calib`-Kalibrierung manuell erzeugen willst |

---

## 2. Plugin installieren

1. Kopiere `Fuses/InstaReframeX6.fuse` in **einen** dieser Ordner:
   - `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Fuses\`
   - oder `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Fuses\`
2. Starte DaVinci Resolve neu.
3. Prüfen: Auf der Fusion-Seite in der Effekt-Bibliothek unter
   `Fuses\Insta360` — das Tool erscheint als **X6R**. Alternativ
   **Shift+Space** drücken und „InstaReframeX6" eingeben.

---

## 3. Weg A — Vollautomatisch (empfohlen)

Das Import-Skript macht alles: Split, Kalibrierung, Import, Timeline.

1. **Skript ausführen**: In Resolve unter
   `Workspace → Scripts → insta360 → import_insv.lua`.
   (Falls es im Menü nicht erscheint: `Workspace → Scripts → Reload and
   run…` und die Datei manuell wählen.)
2. **Wähle deine `.insv`-Datei** im Dateidialog.
3. Das Skript:
   - splittet die `.insv` verlustfrei in `_lens0.mp4` (Back) und
     `_lens1.mp4` (Front) — beide in `<ordner>\insta_reframe\`
   - erzeugt `lens1.calib` (die Linsenkalibrierung) neben dem Front-Clip
   - importiert beide Clips in die Mediathek
   - fügt sie in die Timeline ein: **V1 = lens0 (Back), V2 = lens1 (Front)**
4. Du solltest eine Meldung wie `Importiert: 2` / `Timeline: true` sehen.

### 3.1 Fuse in der Fusion-Seite verdrahten

1. Setze den Playhead auf den V2-Clip (Front) und wechsle auf die
   **Fusion-Seite** (Button in der oberen Werkzeugleiste, oder `Shift+6`).
2. Die Clip-Comp öffnet sich. Du siehst einen `MediaIn1`-Knoten, der bereits
   mit `MediaOut1` verbunden ist.
3. **Back-Stream einfügen**: In der Mediathek (linkes Panel) den
   `_lens0.mp4`-Clip (Bin „Master") suchen und **mit der Maus in den
   Node-Graphen ziehen** (Drag & Drop). Es erscheint ein neuer
   `MediaIn2`-Knoten — das ist der einzige Weg in Resolve 21 (per Skript
   setzen wird von Resolve blockiert).
4. **Fuse hinzufügen**: **Shift+Space** drücken, `InstaReframeX6` eingeben,
   Enter. Ein Knoten mit dem **X6R**-Symbol erscheint.
5. **Verdrahten** (vom grünen Ausgang zum Eingang ziehen):
   ```
   MediaIn1 (lens1/Front) → Fuse „Front"
   MediaIn2 (lens0/Back)  → Fuse „Back"
   Fuse-Output            → MediaOut1 „Input"
   ```

> 💡 **Tipp**: Wenn du den Fuse-Knoten anklickst, zeigt der Inspector rechts
> die Parameter. Falls die Front/Back-Eingänge nicht erscheinen: im
> Inspector **„Neu laden"** klicken.

### 3.2 Bild einstellen

1. Fuse-Knoten auswählen.
2. Im **Inspector** einstellen:
   - **Aspect Ratio**: z. B. `4K UHD` für 16:9, `9:16` für Reels/TikTok
   - **FOV**: gewünschtes Sichtfeld (mit 60–80 beginnen)
3. **Umschauen** mit den Reglern **Pan / Tilt / Roll** — oder das
   **Aim-Fadenkreuz** direkt im Viewer ziehen.

### 3.3 Stitching-Linie korrigieren (Naht-Feinabgleich)

Wenn du an der Naht (Front/Back-Übergang) einen kleinen Versatz siehst:

1. Drehe die Ansicht so, dass die Naht im Viewer gut sichtbar ist.
2. Bewege langsam **BackYaw** (horizontal), bis die Wand/Kante durchgehend
   über die Naht läuft.
3. Bleibt ein vertikaler Versatz, ergänze **BackPitch**.
4. Typische Werte liegen zwischen −1° und +1°.

---

## 4. Weg B — Manueller Workflow

Wenn du die Streams lieber selbst vorbereitest:

1. **`.insv` splitten** (verlustfrei, keine Qualitätsverluste):
   ```bash
   ffmpeg -i VID_xxxx.insv -map 0:0 -c copy lens0.mp4
   ffmpeg -i VID_xxxx.insv -map 0:1 -c copy lens1.mp4
   ```
   (Windows: `scripts/split_insv.bat` per Doppelklick, nachdem eine `.insv`
   im gleichen Ordner liegt, oder per Kommandozeile.)
2. **Kalibrierung erzeugen** (optional, aber empfohlen):
   ```bash
   python tools/insv_calib.py VID_xxxx.insv -o lens1.calib
   ```
   → erzeugt `lens1.calib` neben dem Front-Clip. Der Fuse findet sie beim
   Rendern automatisch.
3. In der Edit-Seite lens1 (Front) auf **V2** und lens0 (Back) auf **V1**
   legen.
4. Weiter bei Schritt **3.1** (Fuse verdrahten) — gleiche Vorgehensweise.

---

## 5. In 4K rendern

1. Auf der **Deliver-Seite** dein Format wählen (z. B. MP4/H.265, 3840×2160,
   oder 1080×1920 für 9:16).
2. Falls du im Fuse Aspect=Custom gewählt hast, dort OutWidth/OutHeight
   setzen.
3. In die Render-Warteschlange legen und rendern.

> ⚠️ **Hinweis**: In einer Clip-Comp beeinflusst auch das Comp-Format die
> Anzeige. Wirkt das Ergebnis beschnitten, prüfe, ob die
> Projekt-Einstellungen (Timeline-Auflösung) zum Aspect-Preset passen.

---

## 6. Problemlösung

| Problem | Lösung |
|---|---|
| Tool nicht in der Effekt-Bibliothek | Resolve neu starten; Fuse-Ordnerpfad prüfen (Schritt 2) |
| Viewer zeigt schwarz | Prüfen, ob `Front` und `Back` verbunden sind; auf dem Fuse **„Neu laden"** klicken |
| Back lässt sich nicht per Skript laden | Der zweite Stream kann in Resolve 21 nur per **Drag & Drop** aus der Mediathek eingefügt werden |
| Kalibrierung wird nicht geladen | Sicherstellen, dass `lens1.calib` im gleichen Ordner wie der Front-Clip liegt; der Fuse liest sie automatisch |
| Naht-Versatz bei nahen Objekten (< ~3 m) | Das ist physikalische Parallaxe (zwei Linsen sehen aus leicht versetzten Positionen). Mit BackYaw/BackPitch reduzieren; Insta360 Studio nutzt dafür ein nicht reproduzierbares KI-Modell |
| Regler-Änderung zeigt keine Wirkung | Im Inspector **„Neu laden"** klicken, dann Regler erneut bewegen |

---

*Feedback, Probleme und Feature-Wünsche: gerne als GitHub-Issue oder Fork
des Repositories.*
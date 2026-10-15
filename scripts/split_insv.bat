@echo off
REM Verlustfreier Split eines Insta360-X6-INSV in die zwei Fisheye-Streams.
REM Verwendung:  split_insv.bat "Pfad\zur\Datei.insv"
REM Ergebnis:    lens0.mp4 (Stream 0 = Back) und lens1.mp4 (Stream 1 = Front)
REM              im Cloud-Ordner der Eingabedatei.
setlocal enabledelayedexpansion

if "%~1"=="" (
    echo Bitte Datei angeben: split_insv.bat "C:\pfad\VID_xxxx.insv"
    exit /b 1
)

set "IN=%~f1"
set "DIR=%~dp1"

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ffmpeg wurde nicht gefunden. Bitte ffmpeg zum PATH hinzufuegen.
    exit /b 1
)

ffmpeg -y -i "%IN%" -map 0:0 -c copy "%DIR%lens0.mp4" || goto :err
ffmpeg -y -i "%IN%" -map 0:1 -c copy "%DIR%lens1.mp4" || goto :err

echo.
echo Fertig:
echo   %DIR%lens0.mp4   (Stream 0 = Back)
echo   %DIR%lens1.mp4   (Stream 1 = Front)
exit /b 0

:err
echo FEHLER beim Verarbeiten von "%IN%"
exit /b 1
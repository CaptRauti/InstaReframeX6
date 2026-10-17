"""metadata.py — UTC creation time & duration of a video clip.

Resolution order (Insta360 reality: split .mp4 lose creation_time via
ffmpeg -c copy, the original .insv keeps it):

  1. ffprobe creation_time of the given file (GoPro/phone MP4 work directly)
  2. Sidecar/original .insv lookup (strip _lensN.mp4, search parent dirs)
  3. Insta360 filename pattern VID_YYYYMMDD_HHMMSS -> local time -> UTC

All timestamps are returned as UTC-aware datetimes.
"""
import os
import re
import json
import subprocess
from datetime import datetime, timezone

FFPROBE = "ffprobe"

# ffprobe flags: format tags + duration + video stream fps/frames
_PROBE_JSON = [
    "-v", "error",
    "-show_entries", "format=duration:format_tags=creation_time",
    "-show_entries", "stream=codec_type,r_frame_rate,nb_frames",
    "-of", "json",
]


def probe_video(path, ffprobe=FFPROBE):
    """Extract UTC creation_time, duration (ms), fps, frame count.

    Returns dict: creation_utc (datetime|None), duration_ms (int),
    fps (float|None), nb_frames (int|None), path.
    """
    out = subprocess.run([ffprobe] + _PROBE_JSON + [path],
                         capture_output=True, text=True)
    d = json.loads(out.stdout)
    fmt = d.get("format", {})
    ct = fmt.get("tags", {}).get("creation_time")
    creation = None
    if ct:
        creation = datetime.fromisoformat(ct.replace("Z", "+00:00"))
        if creation.tzinfo is None:
            creation = creation.replace(tzinfo=timezone.utc)
    dur = float(fmt.get("duration", 0))
    fps = None
    frames = None
    for s in d.get("streams", []):
        if s.get("codec_type") == "video":
            fr = s.get("r_frame_rate", "")
            if "/" in fr:
                n, dn = fr.split("/")
                fps = float(n) / float(dn)
            if s.get("nb_frames"):
                frames = int(s["nb_frames"])
    return {"creation_utc": creation, "duration_ms": int(round(dur * 1000)),
            "fps": fps, "nb_frames": frames, "path": path}


_INSTA_RE = re.compile(r"VID_?(\d{8})_(\d{6})")


def _insta360_filename_utc(path):
    """VID_YYYYMMDD_HHMMSS = camera LOCAL time -> convert to UTC via local tz."""
    m = _INSTA_RE.search(os.path.basename(path))
    if not m:
        return None
    naive = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    return naive.astimezone()  # local tz -> aware


def _sidecar_insv(path):
    """Find the original .insv for a split clip (strip _lensN.mp4)."""
    base = os.path.basename(path)
    stem = re.sub(r"_lens\d+\.(mp4|mov)$", "", base)
    stem = re.sub(r"\.(mp4|mov)$", "", stem)
    for d in (os.path.dirname(path), os.path.dirname(os.path.dirname(path))):
        cand = os.path.join(d, stem + ".insv")
        if os.path.isfile(cand):
            return cand
    return None


def clip_start_utc(path, ffprobe=FFPROBE):
    """Resolve the clip's absolute UTC start. Returns (datetime, source_tag)."""
    info = probe_video(path, ffprobe)
    if info["creation_utc"]:
        return info["creation_utc"], "ffprobe"
    side = _sidecar_insv(path)
    if side:
        probe = probe_video(side, ffprobe)
        if probe["creation_utc"]:
            return probe["creation_utc"], "insv-sidecar"
    fn = _insta360_filename_utc(path)
    if fn:
        return fn, "filename"
    raise ValueError("no UTC creation time found for %s" % path)
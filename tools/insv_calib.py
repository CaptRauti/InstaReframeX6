#!/usr/bin/env python3
"""insv_calib.py — erzeugt aus einer Insta360-X6-INSV-Datei eine kompakte
Kalibrierungs-Datei (*.calib) im Klartext-Format Key=Value, die der
InstaReframeX6-Fuse direkt liest (Auto-Kalibrierung pro Aufnahme).

Keine externen Abhängigkeiten — nur Python-Standardbibliothek.
Modell/Konventionen exakt wie im verifizierten Fuse v1.0 und
insv-stitch/stitch_engine (build_lenses mit swap=True -> [Front, Back]):

  Front = Stream 1 (raw[1]):  Extrinsik R.T @ ray, nur yaw/pitch-Korrektur
  Back  = Stream 0 (raw[0]):  Extrinsik (Ry180 * R) .T @ ray

Verwendung:
  python insv_calib.py <datei.insv> [-o out.calib]

Format (eine Zeile je Wert, Punkt als Dezimaltrennzeichen):
  front_xi=2.45543
  front_fx=3611.11
  front_m00=0.999973
  ...
  back_s4=-0.00159663
"""
import os
import math
import struct
import argparse

SIG = b'8db42d694ccc418790edff439fe026bf'
TYPES = {0: 'INDEX', 1: 'INFO', 2: 'THUMBNAIL', 3: 'GYRO', 4: 'EXPOSURE',
         5: 'THUMBNAIL_EXT', 6: 'TIMELAPSE', 7: 'GPS', 8: 'STAR_NUM',
         9: 'AAA_TIMESTAMP', 10: 'ANCHORS', 11: 'AAA_SIMULATION',
         12: 'EXPOSURE_SECONDARY', 13: 'MAGNETIC', 14: 'EULER', 15: 'GYRO_SECONDARY',
         16: 'SPEED', 17: 'TBOX', 18: 'EDITOR', 19: 'HEARTRATE',
         20: 'FORWARD_DIRECTION', 21: 'UPVIEW', 22: 'SHELL_RECOGNITION',
         23: 'POS', 24: 'TIMELAPSE_QUAT', 25: 'QUATERNION',
         51: 'ONLINE_QUATERNION', 128: 'TIMEMAP'}
HDR = 6


# ---------------- INSV-Metadaten-Parser (pure stdlib) ----------------

def read_frames(path):
    """Liefert {type_name: payload} aller Metadaten-Frames."""
    with open(path, 'rb') as f:
        n = f.seek(0, 2)
        f.seek(n - 72)
        tail = f.read(72)
        if tail[40:72] != SIG:
            raise ValueError('keine v3-Metadaten-Signatur - kein unterstuetztes .insv')
        meta_size, version = struct.unpack('<ii', tail[32:40])
        meta_pos = n - meta_size
        out = {}
        cur = n - 72
        while cur > meta_pos:
            f.seek(cur - HDR)
            h = f.read(HDR)
            if len(h) < HDR:
                break
            code = h[1]
            size = struct.unpack('<I', h[2:6])[0]
            name = TYPES.get(code)
            if name is None or size <= 0 or size > meta_size:
                break
            pos = cur - size - HDR
            f.seek(pos)
            out[name] = f.read(size)
            cur = pos
    return out, version, meta_size


def _read_varint(b, i):
    v = 0
    shift = 0
    while True:
        x = b[i]
        i += 1
        v |= (x & 0x7f) << shift
        if not (x & 0x80):
            return v, i
        shift += 7


def pb_fields(b):
    """Shallow protobuf walk: yields (field_number, wire_type, value)."""
    i = 0
    while i < len(b):
        key, i = _read_varint(b, i)
        fn, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _read_varint(b, i)
            yield fn, 'v', v
        elif wt == 1:
            yield fn, 'd', int.from_bytes(b[i:i + 8], 'little')
            i += 8
        elif wt == 2:
            ln, i = _read_varint(b, i)
            yield fn, 'b', b[i:i + ln]
            i += ln
        elif wt == 5:
            yield fn, 'f', int.from_bytes(b[i:i + 4], 'little')
            i += 4
        else:
            return


def parse_calib_string(s):
    """27 Felder je Linse: xi fx fy cx cy yaw pitch roll tx ty tz d[0..12] sw sh type."""
    vals = [float(p) for p in s.split('_')]
    lenses = []
    i = 1
    while i + 26 < len(vals):
        xi, fx, fy, cx, cy = vals[i:i + 5]
        yaw, pitch, roll = vals[i + 5:i + 8]
        tx, ty, tz = vals[i + 8:i + 11]
        d = vals[i + 11:i + 24]
        sensor_w, sensor_h, ltype = int(vals[i + 24]), int(vals[i + 25]), int(vals[i + 26])
        # 13-Koeffizienten-Layout (insv-stitch-Mapping):
        # d[0..3]=k1..k4, d[4]=ungenutzt, d[5]=p1, d[6]=p2, d[7..10]=s1..s4
        lenses.append(dict(xi=xi, fx=fx, fy=fy, cx=cx, cy=cy,
                           yaw=yaw, pitch=pitch, roll=roll,
                           tx=tx, ty=ty, tz=tz,
                           k1=d[0], k2=d[1], k3=d[2], k4=d[3],
                           p1=d[5], p2=d[6],
                           s1=d[7], s2=d[8], s3=d[9], s4=d[10],
                           d=d, sensor_w=sensor_w, sensor_h=sensor_h, type=ltype))
        i += 27
    return lenses


def extract_calib(path):
    """Gibt rohe Linsen-Kalibrierung + Video-Abmessungen zurueck."""
    frames, version, _ = read_frames(path)
    info = frames.get('INFO')
    if not info:
        raise ValueError('kein INFO-Frame - keine Kalibrierung')
    video_w = video_h = None
    crop_w = crop_h = None
    calib_strings = []
    for fn, wt, v in pb_fields(info):
        if wt == 'b':
            if fn in (111, 112) and b'_' in v:
                calib_strings.append(v.decode('latin1'))
            elif fn == 19:
                sub = list(pb_fields(v))
                video_w, video_h = sub[0][2], sub[1][2]
            elif fn == 27:
                sub = list(pb_fields(v))
                crop_w, crop_h = sub[2][2], sub[3][2]
    if not calib_strings:
        raise ValueError('keine Kalibrierungs-Strings im INFO-Frame')
    return dict(video_w=video_w, video_h=video_h, crop_w=crop_w, crop_h=crop_h,
                raw=parse_calib_string(calib_strings[0]))


# ---------------- Extrinsik (reiner math, scipy-Konvention) ----------------

def _mm(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def R_yaw_pitch(yaw, pitch):
    """R = Ry(yaw) @ Rx(pitch) in Grad (scipy from_euler('YX')-Konvention)."""
    y, p = math.radians(yaw), math.radians(pitch)
    Sy, Cy = math.sin(y), math.cos(y)
    Sp, Cp = math.sin(p), math.cos(p)
    Ry = [[Cy, 0.0, Sy], [0.0, 1.0, 0.0], [-Sy, 0.0, Cy]]
    Rx = [[1.0, 0.0, 0.0], [0.0, Cp, -Sp], [0.0, Sp, Cp]]
    return _mm(Ry, Rx)


def extrinsik_RT(yaw, pitch, back):
    """Liefert R.T als 9 Werte (R.T @ Vec), Back mit 180°-Y davor."""
    R = R_yaw_pitch(yaw, pitch)
    if back:
        Ry180 = [[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]]
        R = _mm(Ry180, R)
    return [R[j][i] for i in range(3) for j in range(3)]  # transponiert


def _video_scale(L, raw, video_w, crop_w):
    """Sensor->Video-Skalierung (Fuse-Konvention aus insv_extract)."""
    scale = video_w / crop_w
    strip_w = raw[0]['sensor_w'] // len(raw)
    cx_local = L['cx'] - 0  # pro-Linse hier: k bestimmt im Aufrufer
    return scale, cx_local, strip_w


def write_calib(path, out):
    meta = extract_calib(path)
    raw = meta['raw']
    if len(raw) < 2:
        raise ValueError('weniger als 2 Linsen in der Kalibrierung')
    scale = meta['video_w'] / meta['crop_w']
    strip_w = raw[0]['sensor_w'] // len(raw)
    # Front = Stream 1 (raw[1]), Back = Stream 0 (raw[0])
    front, back = raw[1], raw[0]
    with open(out, 'w', encoding='ascii') as f:
        f.write('# InstaReframeX6 Kalibrierung\n')
        f.write('# Quelle: %s\n' % os.path.basename(path))
        f.write('# Format: Key=Value (eine Zeile je Wert)\n')
        f.write('source=%s\n' % os.path.basename(path))
        f.write('video_w=%d\n' % meta['video_w'])
        f.write('video_h=%d\n' % meta['video_h'])
        for prefix, L, k, is_back in (('front_', front, 1, False),
                                      ('back_', back, 0, True)):
            cx_local = L['cx'] - k * strip_w
            f.write('%sxi=%.5f\n' % (prefix, L['xi']))
            f.write('%sfx=%.4f\n' % (prefix, L['fx'] * scale))
            f.write('%sfy=%.4f\n' % (prefix, L['fy'] * scale))
            f.write('%scx=%.4f\n' % (prefix, cx_local * scale))
            f.write('%scy=%.4f\n' % (prefix, L['cy'] * scale))
            for ko in ('k1', 'k2', 'k3', 'k4', 'p1', 'p2', 's1', 's2', 's3', 's4'):
                f.write('%s%s=%.8g\n' % (prefix, ko, L[ko]))
            m = extrinsik_RT(L['yaw'], L['pitch'], is_back)
            for j, v in enumerate(m):
                f.write('%sm%d=%.6f\n' % (prefix, j, v))
    print('OK: %d Bytes -> %s' % (os.path.getsize(out), out))


def main():
    ap = argparse.ArgumentParser(description='INSV -> .calib Kalibrierungsdatei')
    ap.add_argument('insv')
    ap.add_argument('-o', '--out')
    a = ap.parse_args()
    out = a.out or os.path.splitext(a.insv)[0] + '.calib'
    write_calib(a.insv, out)


if __name__ == '__main__':
    main()
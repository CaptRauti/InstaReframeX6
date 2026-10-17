"""make_test_gpx.py — synthetic GPX for end-to-end tests.

Generates a realistic drive (accelerating, turning, climbing) in UTC
anchored to a given clip start. Used to validate slicer + renderer.
"""
import math
from datetime import datetime, timedelta, timezone


def make_gpx(path, start_utc, duration_s=6.0, samples_per_s=10.0,
             start_speed=0.0, heading=90.0, lat0=51.9, lon0=9.45, alt0=110.0):
    """Write a GPX covering [start, start+duration] at samples_per_s points."""
    dt = 1.0 / samples_per_s
    lat, lon = lat0, lon0
    speed = start_speed
    pts = []
    t0 = start_utc
    n = int(duration_s * samples_per_s) + 1
    for i in range(n):
        # speed profile: accelerate to 60 km/h, slight wobble
        speed = 16.67 * min(1.0, i / (n * 0.4)) + 2.0 * math.sin(i * 0.35)
        speed = max(0.0, speed)
        heading = (90.0 + 40.0 * math.sin(i * 0.12)) % 360.0
        alt = alt0 + 12.0 * math.sin(i * 0.08) + i * 0.05
        # integrate position
        dist = speed * dt
        ha = math.radians(heading)
        lat += dist * math.cos(ha) / 111320.0
        lon += dist * math.sin(ha) / (111320.0 * math.cos(math.radians(lat)))
        pts.append((t0 + timedelta(seconds=i * dt), lat, lon, alt))
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<gpx version="1.1" creator="gpxtelemetry-test">\n'
                '<trk><name>test</name><trkseg>\n')
        for t, la, lo, el in pts:
            f.write('<trkpt lat="%.7f" lon="%.7f">'
                    '<ele>%.2f</ele>'
                    '<time>%s</time></trkpt>\n' % (la, lo, el,
                    t.strftime("%Y-%m-%dT%H:%M:%S.") + "%06dZ" % t.microsecond))
        f.write('</trkseg></trk>\n</gpx>\n')
    return len(pts)


if __name__ == "__main__":
    import sys
    start = datetime(2026, 9, 18, 18, 55, 57, tzinfo=timezone.utc)
    n = make_gpx(sys.argv[1] if len(sys.argv) > 1 else "test.gpx", start,
                 duration_s=3.0)
    print("wrote %d points" % n)

"""gpxtelemetry — GPX telemetry overlay engine for action-cam footage.

Dual strategy:
  Strategy A: transparent ProRes/QTRLE alpha overlay video (overlay_renderer)
  Strategy B: Fusion keyframe/data payloads for InstaReframeX6 (fusion_gpx_bridge)

Core: gpx_time_slicer — clip-UTC-anchored GPX slicing + frame-accurate
interpolation. Pure stdlib + numpy, no external deps.
"""
from .gpx_time_slicer import slice_gpx, TelemetryFrame
from .metadata import probe_video, clip_start_utc
from .gpx_parser import parse_gpx, GpxPoint

__version__ = "0.1.0"
__all__ = ["slice_gpx", "TelemetryFrame", "probe_video", "clip_start_utc",
           "parse_gpx", "GpxPoint"]
from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass(frozen=True)
class ProjectionMetadata:
    perspective_point_height: float
    longitude_of_projection_origin: float
    sweep_angle_axis: str
    semi_major_axis: float
    semi_minor_axis: float


@dataclass(frozen=True)
class Scene:
    data: np.ndarray
    x_scan_rad: np.ndarray
    y_scan_rad: np.ndarray
    projection: ProjectionMetadata
    platform: str
    logical_band: str
    source_channels: tuple[str, ...]
    unit_kind: str
    scan_start: datetime
    scan_end: datetime
    region: str

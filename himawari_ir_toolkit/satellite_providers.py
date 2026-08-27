from dataclasses import dataclass
from datetime import date, datetime
import json
import os
import re
import sys
import urllib.request

import numpy as np


# #region debug-point helper:goes-trial-reporter

def _debug_report(hypothesis_id, location, msg, data=None, run_id="pre-fix"):
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.dbg', 'goes-trial.env')
    url = 'http://127.0.0.1:7777/event'
    session_id = 'goes-trial'
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('DEBUG_SERVER_URL='):
                    url = line.split('=', 1)[1].strip()
                elif line.startswith('DEBUG_SESSION_ID='):
                    session_id = line.split('=', 1)[1].strip()
    except Exception:
        pass
    payload = {
        "sessionId": session_id,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "msg": msg,
        "data": data or {},
    }
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=1,
        ).read()
    except Exception:
        pass

# #endregion

from himawari_ir_toolkit.satellite_scene import ProjectionMetadata, Scene


@dataclass(frozen=True)
class ProviderConfig:
    regions: tuple[str, ...]
    minutes: tuple[int, ...]
    bucket: str | None
    label: str
    archive_start: date | None
    archive_end: date | None


PROVIDER_CONFIGS = {
    "Himawari-9": ProviderConfig(("F", "T"), (0,), None, "Himawari-9", None, None),
    "GOES-16": ProviderConfig(("F",), (0, 10, 20, 30, 40, 50), "noaa-goes16", "GOES-16", date(2017, 12, 18), date(2025, 4, 6)),
    "GOES-17": ProviderConfig(("F",), (0, 10, 20, 30, 40, 50), "noaa-goes17", "GOES-17（历史）", date(2018, 12, 4), date(2023, 1, 10)),
    "GOES-18": ProviderConfig(("F",), (0, 10, 20, 30, 40, 50), "noaa-goes18", "GOES-18", date(2023, 1, 4), None),
    "GOES-19": ProviderConfig(("F",), (0, 10, 20, 30, 40, 50), "noaa-goes19", "GOES-19", date(2025, 4, 7), None),
}


_GOES_CHANNELS = {
    ("IR", "B13"): ("C13",),
    ("IR", "B14"): ("C14",),
    ("WV", "B08"): ("C08",),
    ("WV", "B09"): ("C09",),
    ("WV", "AVG"): ("C08", "C09"),
    ("VIS", "B03"): ("C02",),
}
_CMIPF_RE = re.compile(
    r"(?:^|/)OR_ABI-L2-CMIPF-M\dC(?P<channel>\d+)_G(?P<satellite>\d+)_"
    r"s(?P<start>\d{14})_e(?P<end>\d{14})(?:_c\d{14})?\.nc$"
)


def get_provider_config(platform):
    try:
        return PROVIDER_CONFIGS[platform]
    except KeyError:
        raise ValueError(f"Unknown platform: {platform}") from None


def get_platform_label(platform):
    return get_provider_config(platform).label


def get_archive_window(platform):
    config = get_provider_config(platform)
    return config.archive_start, config.archive_end


def validate_archive_date(platform, requested_time):
    config = get_provider_config(platform)
    if config.archive_start is None and config.archive_end is None:
        return
    requested_date = requested_time.date()
    if (
        (config.archive_start is not None and requested_date < config.archive_start)
        or (config.archive_end is not None and requested_date > config.archive_end)
    ):
        start = config.archive_start.isoformat() if config.archive_start else "起始"
        end = config.archive_end.isoformat() if config.archive_end else "至今"
        separator = " 至 " if config.archive_end is not None else " "
        raise ValueError(
            f"{platform} 可用日期为 {start}{separator}{end}，请求日期为 {requested_date.isoformat()}"
        )


def get_source_channels(platform, data_type, band):
    if get_provider_config(platform).bucket is None:
        raise ValueError(f"Unsupported platform: {platform}")
    try:
        return _GOES_CHANNELS[(data_type, band)]
    except KeyError:
        raise ValueError(f"Unsupported data_type/band: {data_type} {band}") from None


def scene_from_goes_datasets(platform, data_type, band, datasets, scan_start, scan_end):
    processing_error = None
    close_errors = []
    try:
        source_channels = get_source_channels(platform, data_type, band)
        missing_channels = [channel for channel in source_channels if channel not in datasets]
        if missing_channels:
            raise ValueError(f"Missing required channel(s): {', '.join(missing_channels)}")

        arrays = []
        for channel in source_channels:
            data = datasets[channel]["CMI"].values.copy()
            if data.ndim != 2:
                raise ValueError(
                    f"CMI for {channel} has actual shape {data.shape}; expected shape (rows, columns)"
                )
            arrays.append(data)
        expected_shape = arrays[0].shape
        for channel, data in zip(source_channels[1:], arrays[1:]):
            if data.shape != expected_shape:
                raise ValueError(
                    f"CMI for {channel} has actual shape {data.shape}; expected shape {expected_shape}"
                )

        reference = datasets[source_channels[0]]
        projection_fields = (
            "perspective_point_height",
            "longitude_of_projection_origin",
            "sweep_angle_axis",
            "semi_major_axis",
            "semi_minor_axis",
        )
        attrs = reference["goes_imager_projection"].attrs
        missing_projection_fields = [field for field in projection_fields if field not in attrs]
        if missing_projection_fields:
            raise ValueError(
                f"Missing projection attribute(s): {', '.join(missing_projection_fields)}"
            )
        def convert_projection_attrs(source_attrs):
            values = {}
            for field in projection_fields:
                try:
                    values[field] = (
                        str(source_attrs[field])
                        if field == "sweep_angle_axis"
                        else float(source_attrs[field])
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(f"Invalid projection attribute {field}") from error
            return values

        projection_values = convert_projection_attrs(attrs)
        projection = ProjectionMetadata(**projection_values)
        x_scan_rad = reference["x"].values.copy()
        y_scan_rad = reference["y"].values.copy()
        if x_scan_rad.ndim != 1:
            raise ValueError(f"x coordinate must be one-dimensional; actual shape {x_scan_rad.shape}")
        if y_scan_rad.ndim != 1:
            raise ValueError(f"y coordinate must be one-dimensional; actual shape {y_scan_rad.shape}")
        expected_shape = (len(y_scan_rad), len(x_scan_rad))
        if arrays[0].shape != expected_shape:
            raise ValueError(
                f"CMI for {source_channels[0]} has actual shape {arrays[0].shape}; expected shape {expected_shape}"
            )

        for channel in source_channels[1:]:
            other = datasets[channel]
            if not np.array_equal(other["x"].values, x_scan_rad):
                raise ValueError(f"{channel} x coordinate metadata is inconsistent")
            if not np.array_equal(other["y"].values, y_scan_rad):
                raise ValueError(f"{channel} y coordinate metadata is inconsistent")
            other_attrs = other["goes_imager_projection"].attrs
            try:
                other_projection = convert_projection_attrs(other_attrs)
            except ValueError as error:
                raise ValueError(f"{channel} projection metadata is inconsistent: {error}") from error
            for field in projection_fields:
                if other_projection[field] != projection_values[field]:
                    raise ValueError(f"{channel} projection metadata {field} is inconsistent")

        if data_type == "WV" and band == "AVG":
            data = np.median(np.stack(arrays), axis=0)
        else:
            data = arrays[0]
        if data_type in ("IR", "WV"):
            data = data - 273.15
            unit_kind = "brightness_temperature"
        else:
            data = data * 100
            unit_kind = "reflectance"

        return Scene(
            data=data, x_scan_rad=x_scan_rad, y_scan_rad=y_scan_rad,
            projection=projection, platform=platform, logical_band=band,
            source_channels=source_channels, unit_kind=unit_kind,
            scan_start=scan_start, scan_end=scan_end, region="F",
        )
    except BaseException:
        processing_error = sys.exc_info()
        raise
    finally:
        for channel, dataset in datasets.items():
            try:
                dataset.close()
            except BaseException as error:
                close_errors.append((channel, error))
        if processing_error is None and close_errors:
            channels = ", ".join(channel for channel, _ in close_errors)
            raise ValueError(f"Failed to close GOES dataset(s): {channels}") from close_errors[0][1]


def goes_cmipf_prefix(platform, requested_time):
    config = get_provider_config(platform)
    if config.bucket is None:
        raise ValueError(f"Platform is not GOES: {platform}")
    day_of_year = requested_time.timetuple().tm_yday
    return f"{config.bucket}/ABI-L2-CMIPF/{requested_time:%Y}/{day_of_year:03d}/{requested_time:%H}/"


def load_goes_scene(platform, requested_time, data_type, band, *, fs=None, open_dataset=None):
    try:
        config = get_provider_config(platform)
        validate_archive_date(platform, requested_time)
        channels = get_source_channels(platform, data_type, band)
        slot = requested_time.strftime("%Y-%m-%d %H:%M:%S")
        if (
            requested_time.minute not in config.minutes
            or requested_time.second != 0
            or requested_time.microsecond != 0
        ):
            raise ValueError(f"Invalid CMIPF slot for {platform} at {slot} UTC")
        # #region debug-point A:validated-goes-request
        _debug_report("A", "satellite_providers.py:load_goes_scene", "[DEBUG] GOES request validated", {
            "platform": platform,
            "slot": slot,
            "data_type": data_type,
            "band": band,
            "channels": channels,
        })
        # #endregion

        missing = []
        if fs is None:
            try:
                import s3fs
            except ImportError:
                missing.append("s3fs")
        if open_dataset is None:
            try:
                import xarray as xr
            except ImportError:
                missing.append("xarray")
        if missing:
            raise ValueError(f"Missing optional GOES loader package(s): {', '.join(missing)}")
        if fs is None:
            fs = s3fs.S3FileSystem(anon=True)
        if open_dataset is None:
            open_dataset = xr.open_dataset

        prefix = goes_cmipf_prefix(platform, requested_time)
        try:
            paths = [path for path in fs.ls(prefix) if path.startswith(prefix)]
        except FileNotFoundError as error:
            raise ValueError(f"No CMIPF scan for {platform} at {slot} UTC") from error
        # #region debug-point B:listed-goes-objects
        _debug_report("B", "satellite_providers.py:load_goes_scene", "[DEBUG] GOES objects listed", {
            "prefix": prefix,
            "path_count": len(paths),
        })
        # #endregion
        selected = {}
        scan_times = {}
        for channel in channels:
            path = select_goes_scan_object(paths, platform, channel, requested_time)
            parsed = _parse_goes_scan_object(path)
            selected[channel] = path
            scan_times[channel] = (parsed[2], parsed[3])
            # #region debug-point B:selected-goes-channel
            _debug_report("B", "satellite_providers.py:load_goes_scene", "[DEBUG] GOES channel selected", {
                "channel": channel,
                "basename": os.path.basename(path),
                "scan_start": parsed[2].isoformat(),
                "scan_end": parsed[3].isoformat(),
            })
            # #endregion

        if len(set(scan_times.values())) != 1:
            raise ValueError(f"GOES scan time metadata inconsistent for {platform} at {slot} UTC")
        scan_start, scan_end = next(iter(scan_times.values()))

        datasets = {}
        handles = []
        scene_owns_datasets = False
        try:
            for channel in channels:
                handle = fs.open(selected[channel], "rb")
                handles.append(handle)
                datasets[channel] = open_dataset(handle, engine="h5netcdf")
                # #region debug-point C:opened-goes-dataset
                _debug_report("C", "satellite_providers.py:load_goes_scene", "[DEBUG] GOES dataset opened", {
                    "channel": channel,
                })
                # #endregion
            scene_owns_datasets = True
            scene = scene_from_goes_datasets(
                platform, data_type, band, datasets, scan_start, scan_end
            )
            # #region debug-point C:created-goes-scene
            _debug_report("C", "satellite_providers.py:load_goes_scene", "[DEBUG] GOES scene created", {
                "platform": platform,
                "source_channels": scene.source_channels,
                "data_shape": scene.data.shape,
                "x_count": len(scene.x_scan_rad),
                "y_count": len(scene.y_scan_rad),
                "projection_lon0": scene.projection.longitude_of_projection_origin,
            })
            # #endregion
            return scene
        except BaseException:
            if not scene_owns_datasets:
                for dataset in datasets.values():
                    try:
                        dataset.close()
                    except BaseException:
                        pass
            raise
        finally:
            for handle in handles:
                try:
                    handle.close()
                except BaseException:
                    pass
    except BaseException as error:
        # #region debug-point E:goes-loader-error
        _debug_report("E", "satellite_providers.py:load_goes_scene", "[DEBUG] GOES loader raised exception", {
            "error_type": type(error).__name__,
            "error": str(error),
        })
        # #endregion
        raise


def _parse_goes_scan_object(path):
    match = _CMIPF_RE.search(path)
    if not match:
        return None

    def parse_timestamp(value):
        try:
            timestamp = datetime.strptime(value[:13], "%Y%j%H%M%S")
        except ValueError as error:
            raise ValueError(f"Invalid GOES timestamp: {value}") from error
        return timestamp.replace(microsecond=int(value[13]) * 100000)

    return (
        int(match.group("channel")),
        int(match.group("satellite")),
        parse_timestamp(match.group("start")),
        parse_timestamp(match.group("end")),
    )


def select_goes_scan_object(paths, platform, channel, requested_time):
    config = get_provider_config(platform)
    slot = requested_time.strftime("%Y-%m-%d %H:%M:%S")
    if config.bucket is None:
        raise ValueError(f"Platform is not GOES: {platform}")
    if (
        requested_time.minute not in config.minutes
        or requested_time.second != 0
        or requested_time.microsecond != 0
    ):
        raise ValueError(f"Invalid CMIPF slot for {platform} {channel} at {slot} UTC")

    satellite = int(platform.split("-")[1])
    channel_number = int(channel.removeprefix("C"))
    requested_slot = requested_time.strftime("%Y%m%d%H%M")
    matches = []
    for path in paths:
        parsed = _parse_goes_scan_object(path)
        if parsed is None:
            continue
        parsed_channel, parsed_satellite, scan_start, _ = parsed
        if (
            parsed_satellite == satellite
            and parsed_channel == channel_number
            and scan_start.strftime("%Y%m%d%H%M") == requested_slot
        ):
            matches.append((scan_start, path))
    if matches:
        return min(matches)[1]
    raise ValueError(f"No CMIPF scan for {platform} {channel} at {slot} UTC")

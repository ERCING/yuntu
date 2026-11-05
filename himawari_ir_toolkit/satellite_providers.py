from dataclasses import dataclass
from datetime import date, datetime
import os
import re
import sys

import numpy as np

# 三种运行形态都要能工作（与 draw_ir_fulldisk.py 同一套约定）：
#   1. 包内导入（测试 / himawari_ir_toolkit.satellite_providers）→ 相对导入；
#   2. 直接跑脚本 → 顶层名；
#   3. PyInstaller 冻结 → 模块是顶层模块，不存在 himawari_ir_toolkit 包名。
if __package__:
    from .satellite_scene import ProjectionMetadata, Scene
else:
    try:
        from himawari_ir_toolkit.satellite_scene import ProjectionMetadata, Scene
    except ImportError:
        from satellite_scene import ProjectionMetadata, Scene


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


def _apply_system_proxy_env():
    """把 Windows 系统代理同步到环境变量，让 s3fs/botocore 真正用上它。

    背景：botocore 与 s3fs 只读 HTTP_PROXY / HTTPS_PROXY 环境变量，**完全不看
    Windows「Internet 选项」里的系统代理**。国内用户通常只开系统代理（Clash 之类
    的 127.0.0.1:7890），于是程序绕过代理直连 S3，速度可能差一个数量级，而用户
    会以为"挂了代理还是慢"。

    规则：
    - 已有任一代理环境变量则完全不动（尊重用户显式配置）；
    - 只在 ProxyEnable=1 且能解析出主机端口时才写入；
    - 设置 HIMAWARI_NO_SYSTEM_PROXY=1 可彻底关掉这个行为；
    - 非 Windows 或读取失败一律静默跳过，绝不影响主流程。
    """
    if os.environ.get('HIMAWARI_NO_SYSTEM_PROXY'):
        return
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
        if os.environ.get(name):
            return
    if sys.platform != 'win32':
        return
    try:
        import winreg
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            enabled, _ = winreg.QueryValueEx(key, 'ProxyEnable')
            if not enabled:
                return
            server, _ = winreg.QueryValueEx(key, 'ProxyServer')
    except (ImportError, OSError, ValueError):
        return
    if not server:
        return
    # ProxyServer 可能是 "host:port"，也可能是按协议分列的
    # "http=host:port;https=host:port"，两种都要处理。
    candidate = server
    if '=' in server:
        for part in server.split(';'):
            if part.lower().startswith('http='):
                candidate = part.split('=', 1)[1]
                break
        else:
            return
    candidate = candidate.strip()
    if not candidate or ':' not in candidate:
        return
    proxy_url = f'http://{candidate}'
    os.environ['HTTP_PROXY'] = proxy_url
    os.environ['HTTPS_PROXY'] = proxy_url
    # 代理只覆盖外网：本机与内网直连，否则会把自己的本地服务也代理掉
    os.environ.setdefault(
        'NO_PROXY',
        'localhost,127.0.0.1,::1,169.254.0.0/16,10.0.0.0/8,'
        '172.16.0.0/12,192.168.0.0/16',
    )


_apply_system_proxy_env()


def _open_s3_filesystem():
    """创建匿名 S3 文件系统，并设上超时。

    没有超时的话，连接一旦卡住就是无限等待——用户看到的是"界面死了"，
    实际是 aiohttp/botocore 在无声地挂着。这里给连接与读取都加上限，
    让卡死变成一条可读的错误。

    注意：s3fs 在本模块是**惰性导入**的可选依赖（见 load_goes_scene 的
    missing 检查），所以这里不能引用模块级的 s3fs，必须就地导入。
    """
    import s3fs

    return s3fs.S3FileSystem(
        anon=True,
        config_kwargs={
            'connect_timeout': 15,
            'read_timeout': 60,
            'retries': {'max_attempts': 2, 'mode': 'standard'},
        },
    )


def load_goes_scene(platform, requested_time, data_type, band, *, fs=None, open_dataset=None):
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
        fs = _open_s3_filesystem()
    if open_dataset is None:
        open_dataset = xr.open_dataset

    prefix = goes_cmipf_prefix(platform, requested_time)
    try:
        paths = [path for path in fs.ls(prefix) if path.startswith(prefix)]
    except FileNotFoundError as error:
        raise ValueError(f"No CMIPF scan for {platform} at {slot} UTC") from error

    selected = {}
    scan_times = {}
    for channel in channels:
        path = select_goes_scan_object(paths, platform, channel, requested_time)
        parsed = _parse_goes_scan_object(path)
        selected[channel] = path
        scan_times[channel] = (parsed[2], parsed[3])

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
        scene_owns_datasets = True
        return scene_from_goes_datasets(
            platform, data_type, band, datasets, scan_start, scan_end
        )
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

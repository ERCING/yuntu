"""
Himawari-9 卫星云图绘制脚本
使用 pycontrails 从 NOAA S3 读取 Himawari-8/9 数据，
配合 mycolor.py 中的自定义色阶绘制云图。

支持的数据类型:
    IR: 红外窗区 (B14, 11.2μm)
    WV: 水汽 (B08, 6.2μm)
    VIS: 可见光 (B03, 0.64μm)

用法:
    python draw_ir_fulldisk.py                          # 默认: IR, IR-CC, 全圆盘
    python draw_ir_fulldisk.py --time "2025-07-24T06:00" # 指定时间
    python draw_ir_fulldisk.py --scheme IR-WK            # 指定色阶
    python draw_ir_fulldisk.py --data-type WV            # 水汽
    python draw_ir_fulldisk.py --data-type VIS           # 可见光
    python draw_ir_fulldisk.py --region T                # 机动观测区域
    python draw_ir_fulldisk.py --list                     # 列出可用色阶
"""

import sys
import os
import argparse
import json
import urllib.request
import warnings
from datetime import datetime, timezone
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.ticker as mticker
import cartopy.crs as ccrs
import cartopy.feature as cfeature

warnings.filterwarnings('ignore')

# 设置 pycontrails 缓存目录到项目目录，避免沙箱限制
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(PROJECT_DIR, 'pycontrails_cache')
os.makedirs(CACHE_DIR, exist_ok=True)
os.environ['PYCONTRAILS_CACHE_DIR'] = CACHE_DIR

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

# 导入自定义色阶
if __package__:
    from .mycolor import color_map, my_color_map
    from .satellite_providers import get_provider_config, load_goes_scene, validate_archive_date
else:
    PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if PACKAGE_ROOT not in sys.path:
        sys.path.insert(0, PACKAGE_ROOT)
    from himawari_ir_toolkit.mycolor import color_map, my_color_map
    from himawari_ir_toolkit.satellite_providers import get_provider_config, load_goes_scene, validate_archive_date

# ============================================================
# 配置参数
# ============================================================
# 数据类型配置
DATA_TYPES = {
    'IR': {
        'name': '红外窗区',
        'bands': ['B13', 'B14'],
        'band_descriptions': {'B13': '10.8μm 红外窗区', 'B14': '11.2μm 红外窗区'},
        'schemes': ['IR-BD', 'IR-CC', 'IR-CA', 'IR-OTT', 'IR-RAMMB', 'IR-RBTOP', 'IR-WK'],
        'default_scheme': 'IR-CC',
        'default_band': 'B14',
        'is_brightness_temp': True,
        'unit': '°C'
    },
    'WV': {
        'name': '水汽',
        'bands': ['B08', 'B09', 'AVG'],
        'band_descriptions': {'B08': '6.2μm 高层水汽', 'B09': '7.0μm 低层水汽', 'AVG': 'B08/B09混合中值'},
        'schemes': ['WV', 'WV-SSD'],
        'default_scheme': 'WV',
        'default_band': 'AVG',
        'is_brightness_temp': True,
        'unit': '°C'
    },
    'VIS': {
        'name': '可见光',
        'bands': ['B03'],
        'band_descriptions': {'B03': '0.64μm 可见光'},
        'schemes': ['VIS-GRAY', 'VIS-ENH'],
        'default_scheme': 'VIS-GRAY',
        'default_band': 'B03',
        'is_brightness_temp': False,
        'unit': '%'
    }
}

# 默认时间
DEFAULT_TIME = "2025-07-24T06:00:00"


def build_scene_title(scene, data_type):
    channels = "/".join(scene.source_channels)
    return f"{scene.platform} {data_type} {scene.logical_band} ({channels})"


def build_scene_geostationary_crs(scene):
    projection = scene.projection
    globe = ccrs.Globe(
        semimajor_axis=projection.semi_major_axis,
        semiminor_axis=projection.semi_minor_axis,
    )
    return ccrs.Geostationary(
        central_longitude=projection.longitude_of_projection_origin,
        satellite_height=projection.perspective_point_height,
        sweep_axis=projection.sweep_angle_axis,
        globe=globe,
    )


def _download_s3_files_with_progress(
    fs,
    paths,
    progress_callback,
    chunk_size=1024 * 1024,
    total_bytes=None,
    initial_bytes=0,
    file_offset=0,
    file_count=None,
    announce_start=True,
):
    if total_bytes is None:
        total_bytes = sum(int(fs.info(path).get("size", 0) or 0) for path in paths)
    if file_count is None:
        file_count = len(paths)
    downloaded_bytes = initial_bytes
    if announce_start:
        progress_callback(downloaded_bytes, total_bytes, file_offset, file_count)
    contents = []

    for file_index, path in enumerate(paths, start=1):
        expected_size = int(fs.info(path)["size"])
        actual_size = 0
        for attempt in range(3):
            chunks = []
            try:
                with fs.open(path, "rb") as remote_file:
                    while True:
                        chunk = remote_file.read(chunk_size)
                        if not chunk:
                            break
                        chunks.append(chunk)
                content = b"".join(chunks)
                actual_size = len(content)
                if actual_size != expected_size:
                    raise ValueError(
                        f"Incomplete download for {path}: expected {expected_size} bytes, actual {actual_size} bytes"
                    )
                break
            except Exception:
                if attempt == 2:
                    if actual_size != expected_size:
                        raise ValueError(
                            f"Incomplete download for {path}: expected {expected_size} bytes, actual {actual_size} bytes"
                        )
                    raise

        downloaded_bytes += len(content)
        progress_callback(downloaded_bytes, total_bytes, file_offset + file_index, file_count)
        contents.append(content)

    progress_callback(downloaded_bytes, total_bytes, file_count, file_count)
    return contents


def _split_valid_segments(x: np.ndarray, y: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    m = np.isfinite(x) & np.isfinite(y)
    if not np.any(m):
        return []

    idx = np.where(m)[0]
    cuts = np.where(np.diff(idx) > 1)[0]
    start = 0
    segs: list[tuple[np.ndarray, np.ndarray]] = []
    for c in cuts:
        part = idx[start : c + 1]
        segs.append((x[part], y[part]))
        start = c + 1
    part = idx[start:]
    segs.append((x[part], y[part]))
    return segs


def _pick_nearest_point_index(v: np.ndarray, target: float) -> int:
    d = np.abs(v - target)
    return int(np.nanargmin(d))


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def get_render_stride(shape: tuple[int, int], max_dimension: int = 11000) -> int:
    return max(1, int(np.ceil(max(shape) / max_dimension)))


def downsample_for_render(data: np.ndarray, max_dimension: int = 11000) -> np.ndarray:
    step = get_render_stride(data.shape, max_dimension)
    return data[::step, ::step]


def get_decoration_layout_metrics(region_full: str, fig_w: float, fig_h: float, dpi: int) -> dict[str, float]:
    fig_w_px = fig_w * dpi
    fig_h_px = fig_h * dpi

    header_font_px = 42
    header_gap_px = 22
    cbar_width_px = 18
    cbar_gap_px = 10
    cbar_tick_px = 30

    info_fontsize = _clamp(round(header_font_px * 72 / dpi), 11, 22)
    cbar_tick_size = _clamp(round(cbar_tick_px * 72 / dpi), 9, 16)

    # Protect narrow figures from header overlap while keeping large FLDK output readable.
    width_limited_info = _clamp(round(fig_w_px / 80), 6, 22)
    width_limited_ticks = _clamp(round(fig_w_px / 110), 6, 16)
    info_fontsize = min(info_fontsize, width_limited_info)
    cbar_tick_size = min(cbar_tick_size, width_limited_ticks)

    if region_full == "FLDK":
        info_fontsize = 35
        cbar_tick_size = 35

    return {
        "info_fontsize": info_fontsize,
        "cbar_tick_size": cbar_tick_size,
        "header_gap_fig": header_gap_px / fig_h_px,
        "cbar_gap": cbar_gap_px / fig_w_px,
        "cbar_width": max(0.018, cbar_width_px / fig_w_px),
    }


def get_decoration_subplot_adjustments(region_full: str, add_decorations: bool) -> dict[str, float]:
    if not add_decorations:
        return {"left": 0.0, "right": 1.0, "top": 1.0, "bottom": 0.0, "wspace": 0.0}
    if region_full == "Target":
        return {"left": 0.04, "right": 0.905, "top": 0.935, "bottom": 0.035, "wspace": 0.01}
    return {"left": 0.01, "right": 0.945, "top": 0.975, "bottom": 0.01, "wspace": 0.01}


def compute_target_lonlat_bounds(
    geos_crs: ccrs.CRS,
    extent: tuple[float, float, float, float],
    samples: int = 300,
):
    x_min, x_max, y_min, y_max = extent
    xs = np.linspace(x_min, x_max, samples)
    ys = np.linspace(y_min, y_max, samples)

    bx = np.concatenate([xs, xs, np.full_like(ys, x_min), np.full_like(ys, x_max)])
    by = np.concatenate([np.full_like(xs, y_max), np.full_like(xs, y_min), ys, ys])

    pc = ccrs.PlateCarree()
    pts = pc.transform_points(geos_crs, bx, by)
    lon = pts[:, 0]
    lat = pts[:, 1]
    m = np.isfinite(lon) & np.isfinite(lat)
    if not np.any(m):
        return None

    proj4_params = getattr(geos_crs, "proj4_params", {})
    lon0 = float(getattr(proj4_params, "get", lambda *_: 0.0)("lon_0", 0.0))
    lon = lon[m]
    lat = lat[m]
    lon = lon0 + (((lon - lon0 + 180.0) % 360.0) - 180.0)

    lon_min = float(np.nanmin(lon))
    lon_max = float(np.nanmax(lon))
    lat_min = float(np.nanmin(lat))
    lat_max = float(np.nanmax(lat))
    if not (lon_min < lon_max and lat_min < lat_max):
        return None
    return lon_min, lon_max, lat_min, lat_max


def draw_target_graticule_and_labels(
    ax,
    geos_crs: ccrs.CRS,
    extent: tuple[float, float, float, float],
    step_deg: float = 1.0,
    npts: int = 200,
):
    bounds = compute_target_lonlat_bounds(geos_crs, extent, samples=300)
    if bounds is None:
        return

    lon_min, lon_max, lat_min, lat_max = bounds
    lon_ticks = np.arange(np.ceil(lon_min), np.floor(lon_max) + 1e-6, step_deg)
    lat_ticks = np.arange(np.ceil(lat_min), np.floor(lat_max) + 1e-6, step_deg)
    if lon_ticks.size == 0 or lat_ticks.size == 0:
        return

    x_min, x_max, y_min, y_max = extent
    dx = (x_max - x_min) * 0.012
    dy = (y_max - y_min) * 0.012
    x_target = x_min + dx
    y_target = y_min + dy

    pc = ccrs.PlateCarree()
    line_style = dict(color="gray", linewidth=0.25, linestyle="--", alpha=0.35, zorder=3)
    label_bbox = dict(facecolor="white", edgecolor="none", alpha=0.45, boxstyle="square,pad=0.12")

    lat_line = np.linspace(lat_min, lat_max, npts)
    last_lon_label_x_px = None
    for lo in lon_ticks:
        lon_line = np.full_like(lat_line, lo)
        pts = geos_crs.transform_points(pc, lon_line, lat_line)
        x = pts[:, 0]
        y = pts[:, 1]
        for xs, ys in _split_valid_segments(x, y):
            ax.plot(xs, ys, transform=geos_crs, **line_style)

        m = np.isfinite(x) & np.isfinite(y)
        if np.any(m):
            xv = x[m]
            yv = y[m]
            idx = _pick_nearest_point_index(yv, y_target)
            x_pos = float(xv[idx])
            y_pos = float(yv[idx])
            ha = "center"
            if x_pos <= x_min + 2.0 * dx:
                ha = "left"
            elif x_pos >= x_max - 2.0 * dx:
                ha = "right"
            lon_label = int(round(float(lo) % 360.0))
            x_px = ax.transData.transform((x_pos, y_pos))[0]
            if last_lon_label_x_px is not None and abs(x_px - last_lon_label_x_px) < 40.0:
                continue
            ax.text(
                x_pos,
                y_pos,
                f"{lon_label}°E",
                transform=geos_crs,
                fontsize=6,
                color="black",
                ha=ha,
                va="bottom",
                zorder=4,
                bbox=label_bbox,
            )
            last_lon_label_x_px = x_px

    lon_line2 = np.linspace(lon_min, lon_max, npts)
    last_lat_label_y_px = None
    for la in lat_ticks:
        lat_line2 = np.full_like(lon_line2, la)
        pts = geos_crs.transform_points(pc, lon_line2, lat_line2)
        x = pts[:, 0]
        y = pts[:, 1]
        for xs, ys in _split_valid_segments(x, y):
            ax.plot(xs, ys, transform=geos_crs, **line_style)

        m = np.isfinite(x) & np.isfinite(y)
        if np.any(m):
            xv = x[m]
            yv = y[m]
            idx = _pick_nearest_point_index(xv, x_target)
            x_pos = float(xv[idx])
            y_pos = float(yv[idx])
            va = "center"
            if y_pos <= y_min + 2.0 * dy:
                va = "bottom"
            elif y_pos >= y_max - 2.0 * dy:
                va = "top"
            lat_label = int(round(float(la)))
            hemi = "N" if lat_label >= 0 else "S"
            y_px = ax.transData.transform((x_pos, y_pos))[1]
            if last_lat_label_y_px is not None and abs(y_px - last_lat_label_y_px) < 26.0:
                continue
            ax.text(
                x_pos,
                y_pos,
                f"{abs(lat_label)}°{hemi}",
                transform=geos_crs,
                fontsize=6,
                color="black",
                ha="left",
                va=va,
                zorder=4,
                bbox=label_bbox,
            )
            last_lat_label_y_px = y_px


def _resolve_data_type_from_scheme(scheme):
    for data_type, config in DATA_TYPES.items():
        if scheme in config["schemes"]:
            return data_type
    raise ValueError(f"Unknown scheme: {scheme}")


def draw_satellite_scene(scene, scheme, out_path, dpi, add_decorations=False, progress_callback=None):
    data_type = _resolve_data_type_from_scheme(scheme)
    cmap, norm = my_color_map(scheme)
    render_data = scene.data
    x_scan = scene.x_scan_rad
    y_scan = scene.y_scan_rad

    if data_type == "VIS":
        stride = get_render_stride(render_data.shape)
        render_data = render_data[::stride, ::stride]
        x_scan = x_scan[::stride]
        y_scan = y_scan[::stride]

    h = scene.projection.perspective_point_height
    x_proj = h * x_scan
    y_proj = h * y_scan
    src_extent = (x_proj.min(), x_proj.max(), y_proj.min(), y_proj.max())
    geos_crs = build_scene_geostationary_crs(scene)

    ny, nx = render_data.shape
    fig_w = nx / dpi
    fig_h = ny / dpi
    if add_decorations:
        fig_w += 0.12

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor="white")
    try:
        ax = fig.add_subplot(1, 1, 1, projection=geos_crs)
        region_full = scene.region
        plt.subplots_adjust(**get_decoration_subplot_adjustments(region_full, add_decorations))
        cf = ax.imshow(render_data, extent=src_extent, origin="upper", cmap=cmap, norm=norm, interpolation="none")
        ax.set_xlim(x_proj.min(), x_proj.max())
        ax.set_ylim(y_proj.min(), y_proj.max())

        if add_decorations:
            ax.coastlines(resolution="50m", color="black", linewidth=0.8)
            ax.add_feature(cfeature.BORDERS, edgecolor="black", linewidth=0.5)
            fig.patch.set_edgecolor("black")
            fig.patch.set_linewidth(0.1)
            ax_pos = ax.get_position()
            layout = get_decoration_layout_metrics(region_full, fig_w, fig_h, dpi)
            cbar_x = ax_pos.x1 + layout["cbar_gap"]
            cbar_width = layout["cbar_width"]
            header_y = min(0.99, ax_pos.y1 + layout["header_gap_fig"])
            fig.text(ax_pos.x0, header_y, build_scene_title(scene, data_type), ha="left", va="bottom")
            cbar_ax = fig.add_axes([cbar_x, ax_pos.y0, cbar_width, ax_pos.height])
            cbar = plt.colorbar(cf, cax=cbar_ax)
            cbar.ax.tick_params(labelsize=layout["cbar_tick_size"])

        fig.savefig(out_path, dpi=dpi, bbox_inches=None, facecolor="white", edgecolor="none")
        return out_path, scene.data, src_extent
    finally:
        plt.close(fig)


def _extract_render_inputs(da, band, is_bt):
    try:
        values = da.values
        if is_bt:
            data = np.median(values, axis=0) - 273.15 if band == 'AVG' else values[0] - 273.15
        else:
            data = values[0] * 100
        del values
        x_scan = da['x'].values.copy()
        y_scan = da['y'].values.copy()
        return data, x_scan, y_scan
    finally:
        close = getattr(da, 'close', None)
        if close is not None:
            close()


def draw_ir_fulldisk(time_str=DEFAULT_TIME, scheme='IR-CC',
                     out_path=None, dpi=150, region='F', data_type='IR', band=None,
                     add_decorations=False, progress_callback=None, platform='Himawari-9'):
    """
    下载并绘制 Himawari 卫星云图

    Parameters
    ----------
    time_str : str
        UTC 时间字符串，格式 "YYYY-MM-DDTHH:MM:SS"
    scheme : str
        色阶名称
    region : str
        观测区域: 'F'=全圆盘, 'J'=日本区域, 'T'=目标区域(机动观测)
    out_path : str or None
        输出路径，None 则自动生成
    dpi : int
        输出分辨率
    data_type : str
        数据类型: 'IR'=红外, 'WV'=水汽, 'VIS'=可见光
    band : str or None
        波段名称: IR可选B13/B14, WV可选B08/B09/AVG, VIS可选B03
    add_decorations : bool
        是否添加装饰元素: 边框、时间波段信息、色阶柱

    Returns
    -------
    tuple
        (out_path, data, extent)
        out_path: 输出图片路径
        data: 数据数组 (numpy.ndarray)
        extent: 图像范围 (x_min, x_max, y_min, y_max)
    """
    config = get_provider_config(platform)
    if data_type not in DATA_TYPES:
        raise ValueError(f"Unknown data_type: {data_type}")
    dtype_config = DATA_TYPES[data_type]

    if band is None:
        band = dtype_config['default_band']
    if band not in dtype_config['bands']:
        raise ValueError(f"Invalid band for {data_type}: {band}")
    if scheme not in dtype_config['schemes']:
        raise ValueError(f"Invalid scheme for {data_type}: {scheme}")

    region_map = {"F": "FLDK", "J": "Japan", "T": "Target"}
    region_full = region_map.get(region, region)
    if region_full not in region_map.values():
        raise ValueError(f"Invalid region: {region}")

    if config.bucket is not None:
        if region not in config.regions:
            raise ValueError(f"Invalid region for {platform}: {region}")
        try:
            requested_time = datetime.fromisoformat(time_str)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid time_str: {time_str!r}; expected ISO-8601 UTC time") from error
        if requested_time.tzinfo is None:
            requested_time = requested_time.replace(tzinfo=timezone.utc)
        else:
            requested_time = requested_time.astimezone(timezone.utc)
        requested_time = requested_time.replace(tzinfo=None)
        validate_archive_date(platform, requested_time)
        if (
            requested_time.minute not in config.minutes
            or requested_time.second != 0
            or requested_time.microsecond != 0
        ):
            slot = requested_time.strftime("%Y-%m-%d %H:%M:%S")
            raise ValueError(f"Invalid CMIPF slot for {platform} at {slot} UTC")
        # #region debug-point A:validated-goes-request
        _debug_report("A", "draw_ir_fulldisk.py:draw_ir_fulldisk", "[DEBUG] GOES request validated", {
            "platform": platform,
            "time_utc": requested_time.isoformat(),
            "data_type": data_type,
            "band": band,
            "scheme": scheme,
            "region": region,
        })
        # #endregion
        scene = load_goes_scene(platform, requested_time, data_type, band)
        # #region debug-point C:loaded-goes-scene
        _debug_report("C", "draw_ir_fulldisk.py:draw_ir_fulldisk", "[DEBUG] GOES scene loaded", {
            "platform": getattr(scene, "platform", platform),
            "source_channels": getattr(scene, "source_channels", ()),
            "data_shape": getattr(getattr(scene, "data", None), "shape", None),
            "scan_start": getattr(getattr(scene, "scan_start", None), "isoformat", lambda: None)(),
            "scan_end": getattr(getattr(scene, "scan_end", None), "isoformat", lambda: None)(),
        })
        # #endregion
        if out_path is None:
            scan_label = scene.scan_start.strftime("%Y-%m-%d_%H%M%S")
            out_dir = 'data'
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(
                out_dir,
                f"{platform.lower()}_{data_type}_{band}_FLDK_{scan_label}_{scheme}.png",
            )
        # #region debug-point D:render-start
        _debug_report("D", "draw_ir_fulldisk.py:draw_ir_fulldisk", "[DEBUG] GOES render started", {
            "out_path": os.path.basename(out_path),
            "dpi": dpi,
            "decorations": add_decorations,
        })
        # #endregion
        result = draw_satellite_scene(
            scene, scheme, out_path, dpi,
            add_decorations=add_decorations,
            progress_callback=progress_callback,
        )
        # #region debug-point D:render-done
        _debug_report("D", "draw_ir_fulldisk.py:draw_ir_fulldisk", "[DEBUG] GOES render completed", {
            "out_path": os.path.basename(result[0]),
            "data_shape": getattr(result[1], "shape", None),
            "extent": result[2],
        })
        # #endregion
        return result

    from pycontrails.datalib.himawari import Himawari
    is_bt = dtype_config['is_brightness_temp']
    band_desc = dtype_config['band_descriptions'][band]
    region_desc = {"FLDK": "全圆盘", "Japan": "日本区域", "Target": "目标区域"}[region_full]
    
    print(f"[1/3] 下载 Himawari {dtype_config['name']} 数据...")
    print(f"      时间: {time_str}")
    print(f"      区域: {region_desc}")
    print(f"      波段: {band} ({band_desc})")

    # AVG模式需要下载B08和B09两份数据
    if band == 'AVG':
        download_bands = ('B08', 'B09')
        print(f"      下载波段: {', '.join(download_bands)}")
    else:
        download_bands = (band,)
    
    hima = Himawari(region=region_full, bands=download_bands)
    if progress_callback is None:
        da = hima.get(time_str)
    else:
        from pycontrails.datalib.himawari import himawari as himawari_module
        import pandas as pd
        import xarray as xr

        timestamp = pd.Timestamp(time_str).to_pydatetime()
        local_paths = hima._lpaths(timestamp)
        missing_bands = [name for name, path in local_paths.items() if not hima.cachestore.exists(path)]

        if missing_bands:
            remote_paths = hima.s3_rpaths(timestamp)
            paths_by_band = {band_name: remote_paths[band_name] for band_name in missing_bands}
            for band_name, paths in paths_by_band.items():
                if not paths:
                    raise ValueError(f"No data found for band {band_name} at time {timestamp}")
            all_paths = [path for paths in paths_by_band.values() for path in paths]
            total_bytes = sum(int(hima.fs.info(path).get("size", 0) or 0) for path in all_paths)
            downloaded_bytes = 0
            file_offset = 0
            progress_callback(0, total_bytes, 0, len(all_paths))

            for band_name, paths in paths_by_band.items():
                raw_data = _download_s3_files_with_progress(
                    hima.fs,
                    paths,
                    progress_callback,
                    total_bytes=total_bytes,
                    initial_bytes=downloaded_bytes,
                    file_offset=file_offset,
                    file_count=len(all_paths),
                    announce_start=False,
                )
                downloaded_bytes += sum(len(raw_data_part) for raw_data_part in raw_data)
                file_offset += len(paths)
                downloaded = himawari_module._parse_s3_raw_data(raw_data)
                downloaded.to_dataset(name="CMI").to_netcdf(local_paths[band_name])
        else:
            progress_callback(1, 1, 1, 1)

        da = xr.open_mfdataset(
            local_paths.values(),
            concat_dim="band_id",
            combine="nested",
            combine_attrs="override",
            coords="minimal",
            compat="override",
        )["CMI"].sortby("band_id")
    print(f"      原始维度: {da.shape}")
    if data_type == "VIS":
        stride = get_render_stride((da.sizes["y"], da.sizes["x"]))
        if stride > 1:
            da = da.isel(y=slice(None, None, stride), x=slice(None, None, stride))
            print(f"      VIS 渲染采样: 每 {stride} 像素取 1，输出最长边不超过 11000")

    data, x_scan, y_scan = _extract_render_inputs(da, band, is_bt)
    del da

    # 构建投影坐标: x/y 是扫描角(弧度), 乘以卫星高度得到投影坐标(米)
    h = 35785863.0  # 卫星高度 (米)
    x_proj = h * x_scan  # 投影坐标 (米)
    y_proj = h * y_scan
    
    # Target 机动观测: 卫星会机动到目标位置，central_lon 不同于默认 140.7
    # 根据目标位置 (~175E) 计算正确的 central_lon
    if region_full == 'Target':
        # 扫描角中心
        x_scan_center = (x_scan.min() + x_scan.max()) / 2
        # 目标位置约 175E，反推卫星位置
        # lon = arctan(x_scan) + central_lon
        # central_lon = target_lon - arctan(x_scan_center)
        target_lon_approx = 175.0
        central_lon = target_lon_approx - np.degrees(np.arctan(x_scan_center))
        central_lon = round(central_lon, 1)
    else:
        central_lon = 140.7
    
    # 计算经纬度（用于网格线标注）
    lon = np.degrees(np.arctan(x_proj / h)) + central_lon
    lat = np.degrees(np.arctan(y_proj / h))

    # 获取色阶
    cmap, norm = my_color_map(scheme)
    vmin = float(norm.vmin)
    vmax = float(norm.vmax)

    print(f"[2/3] 绘制 {dtype_config['name']} 云图 ({scheme})...")
    if is_bt:
        print(f"      亮温范围: {np.nanmin(data):.1f} ~ {np.nanmax(data):.1f} {dtype_config['unit']}")
    else:
        print(f"      反射率范围: {np.nanmin(data):.1f} ~ {np.nanmax(data):.1f}")
    print(f"      色阶范围: {vmin:.1f} ~ {vmax:.1f}")

    # 创建投影（使用正确的 central_lon）
    geos_crs = ccrs.Geostationary(central_longitude=central_lon,
                                   satellite_height=35785863.0,
                                   sweep_axis='x')
    
    # 判断使用哪种投影方式
    if region_full == 'Target':
        # 机动观测区域: 使用 Geostationary 投影保持原生分辨率
        src_crs = geos_crs
        src_extent = (x_proj.min(), x_proj.max(), y_proj.min(), y_proj.max())
    else:
        # 全圆盘/日本区域: 使用 Geostationary 卫星投影
        src_crs = geos_crs
        src_extent = (x_proj.min(), x_proj.max(), y_proj.min(), y_proj.max())

    # 设置matplotlib字体（解决中文乱码）
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    render_data = data

    # 根据渲染数据尺寸和dpi计算figsize
    ny, nx = render_data.shape
    fig_w = nx / dpi
    fig_h = ny / dpi

    # 装饰模式: 预留右侧色阶柱与顶部信息栏空间
    if add_decorations:
        fig_w += 0.12

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor='white')

    # 创建主绘图区
    ax = fig.add_subplot(1, 1, 1, projection=src_crs)
    
    # 装饰模式: 为顶部信息栏和右侧色标预留紧凑空间
    subplot_adj = get_decoration_subplot_adjustments(region_full, add_decorations)
    plt.subplots_adjust(**subplot_adj)

    # 绘制填色图 - 保持原生分辨率
    cf = ax.imshow(render_data, extent=src_extent, origin='upper',
                   cmap=cmap, norm=norm, interpolation='none')

    # 设置轴范围（贴合数据，不添加额外留白）
    ax.set_xlim(x_proj.min(), x_proj.max())
    ax.set_ylim(y_proj.min(), y_proj.max())
    if region_full == "Target":
        ax.set_xticks([])
        ax.set_yticks([])
        ax.tick_params(
            axis="both",
            which="both",
            bottom=False,
            top=False,
            left=False,
            right=False,
            labelbottom=False,
            labeltop=False,
            labelleft=False,
            labelright=False,
        )
        ax.xaxis.get_offset_text().set_visible(False)
        ax.yaxis.get_offset_text().set_visible(False)

    # 装饰模式: 添加海岸线、边框、标题和色阶柱
    if add_decorations:
        # 添加海岸线和国界
        ax.coastlines(resolution='50m', color='black', linewidth=0.8)
        ax.add_feature(cfeature.BORDERS, edgecolor='black', linewidth=0.5)
        # 添加外边框
        fig.patch.set_edgecolor('black')
        fig.patch.set_linewidth(0.1)

        ax_pos = ax.get_position()
        layout = get_decoration_layout_metrics(region_full, fig_w, fig_h, dpi)
        cbar_gap = layout["cbar_gap"]
        cbar_width = layout["cbar_width"]
        cbar_x = ax_pos.x1 + cbar_gap
        cbar_y = ax_pos.y0
        cbar_h = ax_pos.height
        header_y = min(0.99, ax_pos.y1 + layout["header_gap_fig"])
        info_fontsize = layout["info_fontsize"]
        cbar_tick_size = layout["cbar_tick_size"]
        info_fontweight = 'normal'

        # 顶部信息栏：标题与时间保持同一基线，右侧显示范围
        band_label = band.replace('B', '')
        title_text = f"Himawari-9 {data_type} B{band_label}"
        time_text = time_str.replace('T', ' ')[:-3] + " UTC"
        time_x = ax_pos.x0 + min(0.23, ax_pos.width * 0.43)
        plt.figtext(ax_pos.x0, header_y, title_text,
                    fontsize=info_fontsize, fontweight=info_fontweight,
                    ha='left', va='bottom', color='black')
        plt.figtext(time_x, header_y, time_text,
                    fontsize=info_fontsize, fontweight=info_fontweight,
                    ha='left', va='bottom', color='black')

        # 右上角数据范围信息与顶部信息栏基线对齐
        data_min = np.nanmin(data)
        data_max = np.nanmax(data)
        range_text = f"[dmax, dmin]({band})=({data_max:.1f}, {data_min:.1f})"
        plt.figtext(cbar_x + cbar_width, header_y, range_text,
                    fontsize=info_fontsize, fontweight=info_fontweight,
                    ha='right', va='bottom', color='black')

        # 右侧色阶柱与主图顶部/底部严格对齐
        cbar_ax = fig.add_axes([cbar_x, cbar_y, cbar_width, cbar_h])
        cbar = plt.colorbar(cf, cax=cbar_ax)
        cbar.ax.tick_params(labelsize=cbar_tick_size)

    if out_path is None:
        # 文件名包含日期时间、数据类型、波段和区域，保存到 data 文件夹
        time_label = time_str.replace('T', '_').replace(':', '')
        out_dir = 'data'
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f'himawari_{data_type}_{band}_{region_full}_{time_label}_{scheme}.png')

    print(f"[3/3] 保存图片: {out_path}")
    fig.savefig(out_path, dpi=dpi, bbox_inches=None,
                facecolor='white', edgecolor='none')
    plt.close(fig)
    print(f"      完成! 文件大小: {os.path.getsize(out_path) / 1024:.1f} KB")
    
    # 返回图片路径、数据数组和范围信息
    return out_path, data, src_extent


def list_schemes():
    """列出所有可用色阶"""
    print("可用色阶方案:")
    print("-" * 60)
    for dtype, config in DATA_TYPES.items():
        print(f"\n{dtype} ({config['name']}):")
        for name in config['schemes']:
            data = color_map[name]
            temps = data["Temperature"]
            colors = data["Color"]
            print(f"  {name:12s}  范围: {temps.min():6.1f} ~ {temps.max():6.1f}  "
                  f"({len(temps)} 个断点)")


def build_parser():
    parser = argparse.ArgumentParser(description='Himawari 卫星云图绘制工具')
    parser.add_argument('--time', type=str, default=DEFAULT_TIME,
                        help=f'UTC时间 (格式: YYYY-MM-DDTHH:MM:SS), 默认: {DEFAULT_TIME}')
    parser.add_argument('--scheme', type=str, default=None,
                        help='色阶方案, 默认使用各数据类型的默认色阶')
    parser.add_argument('--data-type', type=str, default='IR',
                        help=f'数据类型: {", ".join(DATA_TYPES.keys())}, 默认: IR')
    parser.add_argument('--band', type=str, default=None,
                        help='波段: IR可选B13/B14, WV可选B08/B09/AVG (WV AVG), VIS可选B03, 默认使用各类型默认波段')
    parser.add_argument('--platform', choices=('Himawari-9', 'GOES-18', 'GOES-19'), default='Himawari-9',
                        help='卫星平台；GOES 限全圆盘和十分钟 UTC 槽位，默认: Himawari-9')
    parser.add_argument('--list', action='store_true',
                        help='列出所有可用色阶')
    parser.add_argument('--dpi', type=int, default=150,
                        help='输出分辨率, 默认: 150')
    parser.add_argument('--out', type=str, default=None,
                        help='输出路径')
    parser.add_argument('--region', type=str, default='F',
                        help='观测区域: F=全圆盘, J=日本区域, T=目标区域(机动观测), 默认: F')
    parser.add_argument('--decorations', action='store_true',
                        help='添加边框、时间波段信息和右侧色阶柱')
    return parser


def main():
    args = build_parser().parse_args()

    if args.list:
        list_schemes()
        sys.exit(0)

    if args.data_type not in DATA_TYPES:
        print(f"错误: 未知数据类型 '{args.data_type}'")
        print(f"可用: {', '.join(DATA_TYPES.keys())}")
        sys.exit(1)

    dtype_config = DATA_TYPES[args.data_type]
    if args.band is not None and args.band not in dtype_config['bands']:
        print(f"错误: 数据类型 {args.data_type} 不支持波段 '{args.band}'")
        print(f"可用波段: {', '.join(dtype_config['bands'])}")
        sys.exit(1)

    if args.scheme is None:
        args.scheme = dtype_config['default_scheme']
    if args.scheme not in dtype_config['schemes']:
        print(f"错误: 数据类型 {args.data_type} 不支持色阶 '{args.scheme}'")
        print(f"可用色阶: {', '.join(dtype_config['schemes'])}")
        sys.exit(1)

    draw_ir_fulldisk(time_str=args.time, scheme=args.scheme,
                     out_path=args.out, dpi=args.dpi,
                     region=args.region, data_type=args.data_type, band=args.band,
                     add_decorations=args.decorations, platform=args.platform)


if __name__ == '__main__':
    main()

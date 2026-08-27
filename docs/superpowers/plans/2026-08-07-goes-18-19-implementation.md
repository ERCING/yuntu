# GOES-18/19 Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add GOES-18 and GOES-19 Full Disk IR, WV, and VIS imagery through a provider layer while retaining existing Himawari products and GUI behavior.

**Architecture:** Introduce normalized scene and provider modules. Himawari and GOES providers own source access, logical-band mapping, conversion, and navigation metadata; the renderer receives a scene and owns only display/output. The GUI selects a satellite and configures valid time, region, product, and band choices from provider metadata.

**Tech Stack:** Python 3.13, unittest, NumPy, xarray, s3fs, h5netcdf, Cartopy, Matplotlib, Tkinter.

---

## File Structure

- Create: `himawari_ir_toolkit/satellite_scene.py` — immutable normalized scene and projection payload shared by providers and renderer.
- Create: `himawari_ir_toolkit/satellite_providers.py` — provider registry, logical-product metadata, Himawari wrapper, GOES S3 discovery and NetCDF reader.
- Modify: `himawari_ir_toolkit/draw_ir_fulldisk.py` — replace direct Himawari assumptions with provider scene loading and metadata-driven rendering.
- Modify: `himawari_ir_toolkit/himawari_gui.py` — add satellite selection and enforce provider-specific time/region rules.
- Create: `himawari_ir_toolkit/tests/test_satellite_providers.py` — unit tests for mapping, GOES object selection, unit conversion, scene navigation and provider validation.
- Modify: `himawari_ir_toolkit/tests/test_download_progress.py` — adapt renderer/API tests to satellite-aware input.
- Modify: `himawari_ir_toolkit/tests/test_gui_threading.py` — add satellite-switching and GOES time/region UI tests.

### Task 1: Define Normalized Scene Types

**Files:**
- Create: `himawari_ir_toolkit/satellite_scene.py`
- Create: `himawari_ir_toolkit/tests/test_satellite_providers.py`

- [ ] **Step 1: Write the failing scene construction test**

```python
from datetime import datetime
import unittest
import numpy as np

from himawari_ir_toolkit.satellite_scene import ProjectionMetadata, Scene


class TestScene(unittest.TestCase):
    def test_scene_retains_normalized_render_metadata(self):
        projection = ProjectionMetadata(
            perspective_point_height=35786023.0,
            longitude_of_projection_origin=-137.2,
            sweep_angle_axis="x",
            semi_major_axis=6378137.0,
            semi_minor_axis=6356752.31414,
        )
        scene = Scene(
            data=np.array([[1.0]]),
            x_scan_rad=np.array([0.0]),
            y_scan_rad=np.array([0.0]),
            projection=projection,
            platform="GOES-18",
            logical_band="B14",
            source_channels=("C14",),
            unit_kind="brightness_temperature",
            scan_start=datetime(2026, 8, 7, 12, 0),
            scan_end=datetime(2026, 8, 7, 12, 10),
            region="F",
        )
        self.assertEqual(scene.platform, "GOES-18")
        self.assertEqual(scene.source_channels, ("C14",))
        self.assertEqual(scene.projection.longitude_of_projection_origin, -137.2)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestScene.test_scene_retains_normalized_render_metadata -v
```

Expected: fail because `satellite_scene` does not exist.

- [ ] **Step 3: Implement immutable scene data classes**

```python
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
```

- [ ] **Step 4: Run the test and verify it passes**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestScene.test_scene_retains_normalized_render_metadata -v
```

Expected: `OK`.

- [ ] **Step 5: Commit the scene contract**

```powershell
git add himawari_ir_toolkit/satellite_scene.py himawari_ir_toolkit/tests/test_satellite_providers.py
git commit -m "feat: add normalized satellite scene contract"
```

### Task 2: Add Provider Metadata and GOES Product Mapping

**Files:**
- Create: `himawari_ir_toolkit/satellite_providers.py`
- Modify: `himawari_ir_toolkit/tests/test_satellite_providers.py`

- [ ] **Step 1: Write the failing mapping tests**

```python
from himawari_ir_toolkit.satellite_providers import get_provider_config, get_source_channels


def test_goes_maps_logical_bands_to_abi_channels(self):
    self.assertEqual(get_source_channels("GOES-18", "IR", "B14"), ("C14",))
    self.assertEqual(get_source_channels("GOES-19", "WV", "B08"), ("C08",))
    self.assertEqual(get_source_channels("GOES-18", "WV", "AVG"), ("C08", "C09"))
    self.assertEqual(get_source_channels("GOES-19", "VIS", "B03"), ("C02",))


def test_goes_only_advertises_full_disk_and_ten_minute_slots(self):
    config = get_provider_config("GOES-18")
    self.assertEqual(config["regions"], ("F",))
    self.assertEqual(config["minutes"], tuple(range(0, 60, 10)))
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers -v
```

Expected: import failure for `satellite_providers`.

- [ ] **Step 3: Implement provider metadata and validated mapping**

```python
PROVIDER_CONFIGS = {
    "Himawari-9": {"regions": ("F", "T"), "minutes": (0,), "bucket": None},
    "GOES-18": {"regions": ("F",), "minutes": tuple(range(0, 60, 10)), "bucket": "noaa-goes18"},
    "GOES-19": {"regions": ("F",), "minutes": tuple(range(0, 60, 10)), "bucket": "noaa-goes19"},
}

GOES_CHANNELS = {
    ("IR", "B13"): ("C13",),
    ("IR", "B14"): ("C14",),
    ("WV", "B08"): ("C08",),
    ("WV", "B09"): ("C09",),
    ("WV", "AVG"): ("C08", "C09"),
    ("VIS", "B03"): ("C02",),
}


def get_provider_config(platform):
    if platform not in PROVIDER_CONFIGS:
        raise ValueError(f"Unknown platform: {platform}")
    return PROVIDER_CONFIGS[platform]


def get_source_channels(platform, data_type, band):
    if platform == "Himawari-9":
        return (band,) if band != "AVG" else ("B08", "B09")
    try:
        return GOES_CHANNELS[(data_type, band)]
    except KeyError as error:
        raise ValueError(f"Unsupported GOES product: {data_type} {band}") from error
```

- [ ] **Step 4: Run the provider tests and verify they pass**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers -v
```

Expected: `OK`.

- [ ] **Step 5: Commit metadata and channel mapping**

```powershell
git add himawari_ir_toolkit/satellite_providers.py himawari_ir_toolkit/tests/test_satellite_providers.py
git commit -m "feat: map logical products to GOES ABI channels"
```

### Task 3: Discover Exact GOES CMIPF Files

**Files:**
- Modify: `himawari_ir_toolkit/satellite_providers.py`
- Modify: `himawari_ir_toolkit/tests/test_satellite_providers.py`

- [ ] **Step 1: Write failing object-prefix and exact-time tests**

```python
from datetime import datetime
from himawari_ir_toolkit.satellite_providers import (
    goes_cmipf_prefix,
    select_goes_scan_object,
)


def test_goes_prefix_uses_utc_year_julian_day_and_hour(self):
    when = datetime(2026, 8, 7, 12, 30)
    self.assertEqual(
        goes_cmipf_prefix("GOES-18", when),
        "noaa-goes18/ABI-L2-CMIPF/2026/219/12/",
    )


def test_goes_selection_requires_exact_scan_start_and_channel(self):
    objects = [
        "noaa-goes18/ABI-L2-CMIPF/2026/219/12/OR_ABI-L2-CMIPF-M6C14_G18_s20262191230170_e20262191239543_c20262191240010.nc",
        "noaa-goes18/ABI-L2-CMIPF/2026/219/12/OR_ABI-L2-CMIPF-M6C14_G18_s20262191240170_e20262191249543_c20262191250010.nc",
    ]
    selected = select_goes_scan_object(objects, "C14", datetime(2026, 8, 7, 12, 30))
    self.assertIn("s20262191230170", selected)
    with self.assertRaisesRegex(ValueError, "No GOES-18 Full Disk scan"):
        select_goes_scan_object(objects, "C14", datetime(2026, 8, 7, 12, 20))
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestGOESDiscovery -v
```

Expected: fail because discovery functions do not exist.

- [ ] **Step 3: Implement strict GOES discovery helpers**

```python
import re
from datetime import datetime

GOES_SCAN_RE = re.compile(
    r"_M6(?P<channel>C\d{2})_G(?P<satellite>\d{2})_s(?P<start>\d{13})_"
)


def goes_cmipf_prefix(platform, when):
    config = get_provider_config(platform)
    if config["bucket"] is None:
        raise ValueError(f"{platform} is not a GOES platform")
    return f"{config['bucket']}/ABI-L2-CMIPF/{when:%Y}/{when:%j}/{when:%H}/"


def parse_goes_scan_start(path):
    match = GOES_SCAN_RE.search(path)
    if match is None:
        raise ValueError(f"Unrecognized GOES CMIPF filename: {path}")
    return match.group("channel"), datetime.strptime(match.group("start")[:11], "%Y%j%H%M")


def select_goes_scan_object(paths, channel, requested_time):
    for path in paths:
        found_channel, scan_start = parse_goes_scan_start(path)
        if found_channel == channel and scan_start == requested_time:
            return path
    raise ValueError(f"No GOES-18 Full Disk scan for {channel} at {requested_time:%Y-%m-%d %H:%M} UTC")
```

Update the error message to include the supplied platform argument rather than hard-coding GOES-18 before committing.

- [ ] **Step 4: Run discovery tests and verify they pass**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestGOESDiscovery -v
```

Expected: `OK`.

- [ ] **Step 5: Commit exact scan selection**

```powershell
git add himawari_ir_toolkit/satellite_providers.py himawari_ir_toolkit/tests/test_satellite_providers.py
git commit -m "feat: discover exact GOES full disk scans"
```

### Task 4: Read GOES CMI and Projection Metadata

**Files:**
- Modify: `himawari_ir_toolkit/satellite_providers.py`
- Modify: `himawari_ir_toolkit/tests/test_satellite_providers.py`

- [ ] **Step 1: Write failing reader tests using an in-memory fake dataset**

```python
import numpy as np
from datetime import datetime
from himawari_ir_toolkit.satellite_providers import scene_from_goes_datasets


def test_goes_ir_scene_converts_kelvin_and_uses_file_projection(self):
    dataset = make_fake_goes_dataset(
        cmi=np.array([[273.15, 274.15]]),
        lon0=-137.2,
        height=35786023.0,
    )
    scene = scene_from_goes_datasets(
        platform="GOES-18",
        data_type="IR",
        band="B14",
        datasets={"C14": dataset},
        scan_start=datetime(2026, 8, 7, 12, 30),
        scan_end=datetime(2026, 8, 7, 12, 40),
    )
    self.assertTrue(np.array_equal(scene.data, np.array([[0.0, 1.0]])))
    self.assertEqual(scene.projection.longitude_of_projection_origin, -137.2)
    self.assertEqual(scene.source_channels, ("C14",))


def test_goes_wv_average_uses_pixel_median_and_closes_both_datasets(self):
    c08 = make_fake_goes_dataset(cmi=np.array([[270.15, 280.15]]))
    c09 = make_fake_goes_dataset(cmi=np.array([[274.15, 276.15]]))
    scene = scene_from_goes_datasets(
        platform="GOES-19", data_type="WV", band="AVG",
        datasets={"C08": c08, "C09": c09},
        scan_start=datetime(2026, 8, 7, 12, 30),
        scan_end=datetime(2026, 8, 7, 12, 40),
    )
    self.assertTrue(np.array_equal(scene.data, np.array([[-1.0, 5.0]])))
    self.assertTrue(c08.closed)
    self.assertTrue(c09.closed)


def test_goes_visible_scene_converts_factor_to_percent(self):
    dataset = make_fake_goes_dataset(cmi=np.array([[0.25]]))
    scene = scene_from_goes_datasets(
        platform="GOES-18", data_type="VIS", band="B03",
        datasets={"C02": dataset},
        scan_start=datetime(2026, 8, 7, 12, 30),
        scan_end=datetime(2026, 8, 7, 12, 40),
    )
    self.assertTrue(np.array_equal(scene.data, np.array([[25.0]])))
```

`make_fake_goes_dataset` must expose `__getitem__`, `CMI.values`, `x.values`, `y.values`, `goes_imager_projection.attrs`, and `close()`.

- [ ] **Step 2: Run the reader tests and verify they fail**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestGOESSceneReader -v
```

Expected: fail because `scene_from_goes_datasets` does not exist.

- [ ] **Step 3: Implement metadata-driven scene construction**

```python
def _projection_from_dataset(dataset):
    attrs = dataset["goes_imager_projection"].attrs
    return ProjectionMetadata(
        perspective_point_height=float(attrs["perspective_point_height"]),
        longitude_of_projection_origin=float(attrs["longitude_of_projection_origin"]),
        sweep_angle_axis=str(attrs["sweep_angle_axis"]),
        semi_major_axis=float(attrs["semi_major_axis"]),
        semi_minor_axis=float(attrs["semi_minor_axis"]),
    )


def scene_from_goes_datasets(platform, data_type, band, datasets, scan_start, scan_end):
    channels = get_source_channels(platform, data_type, band)
    source = datasets[channels[0]]
    try:
        arrays = [datasets[channel]["CMI"].values.copy() for channel in channels]
        if data_type == "VIS":
            data = arrays[0] * 100.0
            unit_kind = "reflectance"
        elif band == "AVG":
            data = np.median(np.stack(arrays), axis=0) - 273.15
            unit_kind = "brightness_temperature"
        else:
            data = arrays[0] - 273.15
            unit_kind = "brightness_temperature"
        return Scene(
            data=data,
            x_scan_rad=source["x"].values.copy(),
            y_scan_rad=source["y"].values.copy(),
            projection=_projection_from_dataset(source),
            platform=platform,
            logical_band=band,
            source_channels=channels,
            unit_kind=unit_kind,
            scan_start=scan_start,
            scan_end=scan_end,
            region="F",
        )
    finally:
        for dataset in datasets.values():
            close = getattr(dataset, "close", None)
            if close is not None:
                close()
```

- [ ] **Step 4: Run reader tests and verify they pass**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestGOESSceneReader -v
```

Expected: `OK`.

- [ ] **Step 5: Commit GOES scene construction**

```powershell
git add himawari_ir_toolkit/satellite_providers.py himawari_ir_toolkit/tests/test_satellite_providers.py
git commit -m "feat: load GOES CMI scenes from source metadata"
```

### Task 5: Add Anonymous S3 GOES Provider Loading

**Files:**
- Modify: `himawari_ir_toolkit/satellite_providers.py`
- Modify: `himawari_ir_toolkit/tests/test_satellite_providers.py`

- [ ] **Step 1: Write a failing fake-S3 provider test**

```python
from unittest.mock import patch
from datetime import datetime
from himawari_ir_toolkit.satellite_providers import load_goes_scene


def test_goes_provider_lists_exact_hour_and_opens_required_channels(self):
    fs = FakeS3FileSystem({
        "noaa-goes18/ABI-L2-CMIPF/2026/219/12/": [
            "noaa-goes18/ABI-L2-CMIPF/2026/219/12/OR_ABI-L2-CMIPF-M6C08_G18_s20262191230170_e20262191239543_c20262191240010.nc",
            "noaa-goes18/ABI-L2-CMIPF/2026/219/12/OR_ABI-L2-CMIPF-M6C09_G18_s20262191230170_e20262191239543_c20262191240010.nc",
        ],
    })
    with patch("himawari_ir_toolkit.satellite_providers.s3fs.S3FileSystem", return_value=fs):
        with patch("himawari_ir_toolkit.satellite_providers.xr.open_dataset", side_effect=make_fake_goes_dataset):
            scene = load_goes_scene("GOES-18", datetime(2026, 8, 7, 12, 30), "WV", "AVG")
    self.assertEqual(scene.source_channels, ("C08", "C09"))
    self.assertEqual(fs.listed_prefixes, ["noaa-goes18/ABI-L2-CMIPF/2026/219/12/"])
```

- [ ] **Step 2: Run the provider test and verify it fails**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestGOESProviderLoading -v
```

Expected: fail because `load_goes_scene` does not exist.

- [ ] **Step 3: Implement anonymous S3 object loading**

```python
import s3fs
import xarray as xr


def load_goes_scene(platform, requested_time, data_type, band):
    if requested_time.minute not in get_provider_config(platform)["minutes"] or requested_time.second:
        raise ValueError("GOES Full Disk requires a UTC ten-minute time slot")
    fs = s3fs.S3FileSystem(anon=True)
    prefix = goes_cmipf_prefix(platform, requested_time)
    paths = fs.ls(prefix)
    channels = get_source_channels(platform, data_type, band)
    selected = {channel: select_goes_scan_object(paths, channel, requested_time, platform) for channel in channels}
    datasets = {
        channel: xr.open_dataset(fs.open(path, "rb"), engine="h5netcdf")
        for channel, path in selected.items()
    }
    scan_start = requested_time
    scan_end = parse_goes_scan_end(next(iter(selected.values())))
    return scene_from_goes_datasets(platform, data_type, band, datasets, scan_start, scan_end)
```

Implement `parse_goes_scan_end` with the filename `eYYYYDDDHHMMSSs` segment. Ensure all already-opened datasets are closed if opening a later required channel fails.

- [ ] **Step 4: Run provider test and verify it passes**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestGOESProviderLoading -v
```

Expected: `OK`.

- [ ] **Step 5: Commit S3 provider loading**

```powershell
git add himawari_ir_toolkit/satellite_providers.py himawari_ir_toolkit/tests/test_satellite_providers.py
git commit -m "feat: load GOES scans from public NOAA S3"
```

### Task 6: Migrate Rendering to Scene Metadata

**Files:**
- Modify: `himawari_ir_toolkit/draw_ir_fulldisk.py`
- Modify: `himawari_ir_toolkit/tests/test_download_progress.py`

- [ ] **Step 1: Write failing renderer tests for source metadata**

```python
from datetime import datetime
from unittest.mock import patch
from himawari_ir_toolkit.satellite_scene import ProjectionMetadata, Scene
from himawari_ir_toolkit.draw_ir_fulldisk import draw_satellite_scene


def test_renderer_uses_scene_projection_origin_not_himawari_constant(self):
    scene = make_scene(lon0=-137.2, platform="GOES-18", band="B14")
    with patch("himawari_ir_toolkit.draw_ir_fulldisk.ccrs.Geostationary") as geos:
        with patch("himawari_ir_toolkit.draw_ir_fulldisk.plt.figure", make_fake_figure):
            draw_satellite_scene(scene, scheme="IR-CC", out_path="out.png", dpi=10)
    self.assertEqual(geos.call_args.kwargs["central_longitude"], -137.2)
    self.assertEqual(geos.call_args.kwargs["satellite_height"], 35786023.0)


def test_renderer_title_identifies_platform_channels_and_actual_scan_time(self):
    scene = make_scene(
        platform="GOES-19", band="AVG", channels=("C08", "C09"),
        scan_start=datetime(2026, 8, 7, 12, 30),
    )
    title = build_scene_title(scene, "WV")
    self.assertEqual(title, "GOES-19 WV AVG (C08/C09)")
```

- [ ] **Step 2: Run renderer tests and verify they fail**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_download_progress.TestSceneRendering -v
```

Expected: fail because scene renderer and title helper do not exist.

- [ ] **Step 3: Implement scene-only rendering functions**

Refactor existing image generation into:

```python
def build_scene_title(scene, data_type):
    return f"{scene.platform} {data_type} {scene.logical_band} ({'/'.join(scene.source_channels)})"


def draw_satellite_scene(scene, scheme, out_path, dpi, add_decorations=False):
    h = scene.projection.perspective_point_height
    x_proj = h * scene.x_scan_rad
    y_proj = h * scene.y_scan_rad
    geos_crs = ccrs.Geostationary(
        central_longitude=scene.projection.longitude_of_projection_origin,
        satellite_height=h,
        sweep_axis=scene.projection.sweep_angle_axis,
        globe=ccrs.Globe(
            semimajor_axis=scene.projection.semi_major_axis,
            semiminor_axis=scene.projection.semi_minor_axis,
        ),
    )
```

Move existing color-map, VIS downsampling, figure, decoration, output, close, and return behavior into this function. Use `scene.scan_start` in output filename and decorations. Preserve Himawari output behavior through its provider scene.

- [ ] **Step 4: Make the public drawing API satellite-aware**

Change the entrypoint to accept `platform="Himawari-9"` and call `load_scene(platform, time, region, data_type, band, progress_callback)`. Preserve its return shape:

```python
def draw_ir_fulldisk(..., platform="Himawari-9"):
    scene = load_scene(platform, time_str, region, data_type, band, progress_callback)
    return draw_satellite_scene(scene, scheme, out_path, dpi, add_decorations)
```

Update function validation so each platform validates its region and time rules before any network access.

- [ ] **Step 5: Run renderer and existing suite**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_download_progress -v
python -m unittest discover -s himawari_ir_toolkit/tests -t . -v
```

Expected: all tests pass. Existing Himawari download-progress tests remain green.

- [ ] **Step 6: Commit renderer migration**

```powershell
git add himawari_ir_toolkit/draw_ir_fulldisk.py himawari_ir_toolkit/tests/test_download_progress.py
git commit -m "refactor: render satellite scenes from provider metadata"
```

### Task 7: Add GUI Satellite Selection and GOES Constraints

**Files:**
- Modify: `himawari_ir_toolkit/himawari_gui.py`
- Modify: `himawari_ir_toolkit/tests/test_gui_threading.py`

- [ ] **Step 1: Write failing GUI configuration tests**

```python
from himawari_ir_toolkit.himawari_gui import HimawariGUI


def test_goes_selection_restricts_region_and_minutes(self):
    app = make_fake_gui(platform="GOES-18")
    HimawariGUI._on_platform_change(app, None)
    self.assertEqual(app.region_var.value, "F (全圆盘)")
    self.assertEqual(app.region_combo.values, ("F (全圆盘)",))
    self.assertEqual(app.time_combo.values, tuple(f"12:{minute:02d}:00" for minute in range(0, 60, 10)))


def test_goes_draw_passes_selected_platform_to_worker(self):
    app = make_drawable_fake_gui(platform="GOES-19", time="12:30:00")
    HimawariGUI._draw_image(app)
    self.assertEqual(app.started_thread.args[-1], "GOES-19")
```

- [ ] **Step 2: Run GUI tests and verify they fail**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_gui_threading.TestGUISatelliteSelection -v
```

Expected: fail because platform UI and callback do not exist.

- [ ] **Step 3: Add the satellite UI and provider-aware controls**

Add a readonly combobox above data type:

```python
self.platform_var = tk.StringVar(value="Himawari-9")
self.platform_combo = ttk.Combobox(
    platform_frame,
    textvariable=self.platform_var,
    values=("Himawari-9", "GOES-18", "GOES-19"),
    state="readonly",
    style="Modern.TCombobox",
)
self.platform_combo.bind("<<ComboboxSelected>>", self._on_platform_change)
```

Implement `_on_platform_change` to obtain `get_provider_config(platform)`, set the region values and selected value, regenerate time strings from allowed minutes while preserving the selected hour, then invoke `_on_type_change(None)`. Pass `platform` into `_draw_worker`, then into `draw_ir_fulldisk(platform=platform, ...)`.

- [ ] **Step 4: Add explicit GOES time validation before starting a worker**

```python
minute = int(time_str.split(":", 1)[0].split(":")[-1])
if platform.startswith("GOES") and minute not in range(0, 60, 10):
    self._show_error_dialog("时间错误", "GOES 全圆盘仅提供每 10 分钟一个时次，请选择 00、10、20、30、40 或 50 分钟。")
    return
```

Use the correctly parsed minutes value from the selected `HH:MM:SS` string.

- [ ] **Step 5: Run GUI and full tests**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_gui_threading -v
python -m unittest discover -s himawari_ir_toolkit/tests -t . -v
```

Expected: all tests pass, including existing task invalidation and progress-reset cases.

- [ ] **Step 6: Commit GUI integration**

```powershell
git add himawari_ir_toolkit/himawari_gui.py himawari_ir_toolkit/tests/test_gui_threading.py
git commit -m "feat: select GOES satellites in the GUI"
```

### Task 8: Validate Packaging and Real NOAA Data

**Files:**
- Modify only if verification exposes a concrete defect: `himawari_ir_toolkit/satellite_providers.py`, `himawari_ir_toolkit/draw_ir_fulldisk.py`, relevant test file.

- [ ] **Step 1: Verify dependencies are available before real reads**

Run:

```powershell
python -c "import s3fs, xarray, h5netcdf; print('GOES reader dependencies OK')"
```

Expected: `GOES reader dependencies OK`. If import fails, add the minimal missing package to the existing packaging/dependency mechanism before proceeding; do not add unrelated libraries.

- [ ] **Step 2: Perform six controlled real-data smoke renders**

Choose a documented GOES-18 and GOES-19 UTC time for which the exact `ABI-L2-CMIPF` objects exist. For each satellite, run IR B14, WV AVG, and VIS B03 with `--out` paths under a temporary ignored directory.

```powershell
python himawari_ir_toolkit/draw_ir_fulldisk.py --platform GOES-18 --time 2026-08-07T12:30:00 --data-type IR --band B14 --out data/goes18_ir.png
python himawari_ir_toolkit/draw_ir_fulldisk.py --platform GOES-18 --time 2026-08-07T12:30:00 --data-type WV --band AVG --out data/goes18_wv.png
python himawari_ir_toolkit/draw_ir_fulldisk.py --platform GOES-18 --time 2026-08-07T12:30:00 --data-type VIS --band B03 --out data/goes18_vis.png
```

Repeat with GOES-19. Confirm each output exists, title includes platform/channel/actual scan time, and coastlines align with the image. Do not keep generated PNGs in version control.

- [ ] **Step 3: Verify a missing exact time produces a user-actionable error**

Run:

```powershell
python himawari_ir_toolkit/draw_ir_fulldisk.py --platform GOES-18 --time 2026-08-07T12:20:00 --data-type IR --band B14
```

Expected: nonzero exit with an error explaining that no exact GOES-18 Full Disk scan exists for the requested UTC time. It must not render a neighboring image.

- [ ] **Step 4: Rebuild and smoke-test the Windows package**

Use the existing PyInstaller command pattern, adding explicit collection only if the smoke build proves that `h5py` or `h5netcdf` is absent. Start the EXE and confirm its satellite selector contains both GOES platforms; do not claim a packaged GOES render succeeded without a real render.

- [ ] **Step 5: Run final full regression suite**

Run:

```powershell
python -m unittest discover -s himawari_ir_toolkit/tests -t . -v
git diff --check
```

Expected: all tests pass and no whitespace errors.

- [ ] **Step 6: Commit only verified defect fixes, then report acceptance evidence**

```powershell
git status --short
git add himawari_ir_toolkit/satellite_providers.py himawari_ir_toolkit/draw_ir_fulldisk.py himawari_ir_toolkit/himawari_gui.py himawari_ir_toolkit/tests
git commit -m "fix: complete GOES smoke-test corrections"
```

Do not create an empty commit. Report the six source images, missing-time error behavior, package result, test count, and any unresolved VIS memory limit.

## Plan Self-Review

- Spec coverage: Tasks 1-2 establish the provider boundary and mappings; Tasks 3-5 implement exact-time public S3 CMI loading; Task 6 makes rendering navigation metadata-driven; Task 7 delivers satellite selection and GOES constraints; Task 8 verifies real data, missing scans, packaging, and regression behavior.
- Scope: No L1b, RGB, animation, non-Full-Disk regions, auto-nearest scan substitution, GK2A, or Meteosat tasks are included.
- Consistency: `Scene`, `ProjectionMetadata`, `get_provider_config`, `get_source_channels`, `load_goes_scene`, and `draw_satellite_scene` use the same names across all tasks.
- No placeholder scan: all implementation steps define file paths, required behavior, test commands, and expected outcomes.

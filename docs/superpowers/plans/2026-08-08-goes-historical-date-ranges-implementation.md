# GOES Historical Date Ranges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add GOES-16 and GOES-17 historical support with satellite-specific date bounds while preserving the existing GOES IR/WV/VIS workflow.

**Architecture:** Extend the existing provider configuration with stable platform identifiers, display labels, and inclusive UTC archive bounds. Expose one pure date validator used by both the drawing API and GUI synchronization; keep S3 bucket derivation and rendering unchanged. The GUI clamps its date control when switching satellites and rejects out-of-window API requests before any S3 listing.

**Tech Stack:** Python 3.13, unittest, datetime, Tkinter/ttk, existing xarray/s3fs provider.

---

## Files

- Modify: `himawari_ir_toolkit/satellite_providers.py` — add GOES-16/17 configs, labels, date bounds, and pure date validation.
- Modify: `himawari_ir_toolkit/draw_ir_fulldisk.py` — validate GOES requested date before `load_goes_scene`.
- Modify: `himawari_ir_toolkit/himawari_gui.py` — show four satellites, display GOES-17 historical label, and clamp date selection after platform changes.
- Modify: `himawari_ir_toolkit/tests/test_satellite_providers.py` — provider configuration and boundary tests.
- Modify: `himawari_ir_toolkit/tests/test_download_progress.py` — drawing API boundary tests.
- Modify: `himawari_ir_toolkit/tests/test_gui_threading.py` — GUI label and date-clamping tests.

### Task 1: Add Historical Provider Configuration

**Files:**
- Modify: `himawari_ir_toolkit/satellite_providers.py`
- Test: `himawari_ir_toolkit/tests/test_satellite_providers.py`

- [ ] **Step 1: Write failing tests for four satellite configs**

```python
from datetime import date
from himawari_ir_toolkit.satellite_providers import (
    get_archive_window,
    get_platform_label,
    get_provider_config,
    validate_archive_date,
)


def test_goes16_and_goes17_have_historical_buckets_and_labels(self):
    self.assertEqual(get_provider_config("GOES-16")["bucket"], "noaa-goes16")
    self.assertEqual(get_provider_config("GOES-17")["bucket"], "noaa-goes17")
    self.assertEqual(get_platform_label("GOES-17"), "GOES-17（历史）")
    self.assertEqual(get_platform_label("GOES-18"), "GOES-18")


def test_archive_windows_are_inclusive(self):
    self.assertEqual(get_archive_window("GOES-16"), (date(2017, 12, 18), date(2025, 4, 6)))
    self.assertEqual(get_archive_window("GOES-17"), (date(2018, 12, 4), date(2023, 1, 10)))
    self.assertEqual(get_archive_window("GOES-18"), (date(2023, 1, 4), None))
    self.assertEqual(get_archive_window("GOES-19"), (date(2025, 4, 7), None))
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestHistoricalProviderConfig -v
```

Expected: import failure because the new helpers/config entries do not exist.

- [ ] **Step 3: Implement the minimal config extension**

```python
from datetime import date

PROVIDER_CONFIGS.update({
    "GOES-16": {
        "regions": ("F",),
        "minutes": tuple(range(0, 60, 10)),
        "bucket": "noaa-goes16",
        "label": "GOES-16",
        "archive_start": date(2017, 12, 18),
        "archive_end": date(2025, 4, 6),
    },
    "GOES-17": {
        "regions": ("F",),
        "minutes": tuple(range(0, 60, 10)),
        "bucket": "noaa-goes17",
        "label": "GOES-17（历史）",
        "archive_start": date(2018, 12, 4),
        "archive_end": date(2023, 1, 10),
    },
    "GOES-18": {
        "label": "GOES-18",
        "archive_start": date(2023, 1, 4),
        "archive_end": None,
    },
    "GOES-19": {
        "label": "GOES-19",
        "archive_start": date(2025, 4, 7),
        "archive_end": None,
    },
})


def get_platform_label(platform):
    return get_provider_config(platform)["label"]


def get_archive_window(platform):
    config = get_provider_config(platform)
    return config["archive_start"], config["archive_end"]
```

Preserve existing GOES-18/19 regions, minutes, and bucket fields when extending the dictionaries.

- [ ] **Step 4: Run provider config tests**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestHistoricalProviderConfig -v
```

Expected: all config tests pass.

- [ ] **Step 5: Commit**

```powershell
git add himawari_ir_toolkit/satellite_providers.py himawari_ir_toolkit/tests/test_satellite_providers.py
git commit -m "feat: configure historical GOES satellites"
```

### Task 2: Validate Archive Dates Before S3 Access

**Files:**
- Modify: `himawari_ir_toolkit/satellite_providers.py`
- Modify: `himawari_ir_toolkit/draw_ir_fulldisk.py`
- Test: `himawari_ir_toolkit/tests/test_satellite_providers.py`
- Test: `himawari_ir_toolkit/tests/test_download_progress.py`

- [ ] **Step 1: Write failing boundary tests**

```python
from datetime import datetime
from unittest.mock import Mock, patch


def test_archive_boundaries_are_inclusive_and_outside_dates_are_rejected(self):
    validate_archive_date("GOES-16", datetime(2025, 4, 6))
    with self.assertRaisesRegex(ValueError, "2017-12-18.*2025-04-06"):
        validate_archive_date("GOES-16", datetime(2025, 4, 7))
    validate_archive_date("GOES-17", datetime(2023, 1, 10))
    with self.assertRaisesRegex(ValueError, "2018-12-04.*2023-01-10"):
        validate_archive_date("GOES-17", datetime(2023, 1, 11))
    validate_archive_date("GOES-18", datetime(2099, 1, 1))


def test_draw_goes_rejects_date_before_loader(self):
    with patch("himawari_ir_toolkit.draw_ir_fulldisk.load_goes_scene") as loader:
        with self.assertRaises(ValueError):
            draw_ir_fulldisk(
                time_str="2024-08-01T09:00:00",
                scheme="IR-CC", region="F", data_type="IR", band="B14",
                platform="GOES-19",
            )
    loader.assert_not_called()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestArchiveDateValidation himawari_ir_toolkit.tests.test_download_progress.TestGOESArchiveDateValidation -v
```

Expected: fail because `validate_archive_date` is not implemented and the drawing API does not call it.

- [ ] **Step 3: Implement pure validation and API guard**

```python
def validate_archive_date(platform, requested_time):
    start, end = get_archive_window(platform)
    requested_date = requested_time.date()
    if requested_date < start or (end is not None and requested_date > end):
        end_text = end.isoformat() if end is not None else "至今"
        raise ValueError(
            f"{platform} 可用归档范围为 {start.isoformat()} 至 {end_text}，"
            f"请求日期为 {requested_date.isoformat()}"
        )
```

Call this in `draw_ir_fulldisk` immediately after parsing/UTC-normalizing `requested_time` and before `load_goes_scene(...)`. Keep existing ten-minute validation unchanged.

- [ ] **Step 4: Run boundary tests and full regression**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_satellite_providers.TestArchiveDateValidation himawari_ir_toolkit.tests.test_download_progress.TestGOESArchiveDateValidation -v
python -m unittest discover -s himawari_ir_toolkit/tests -t . -v
```

Expected: boundary tests pass and all existing tests remain green.

- [ ] **Step 5: Commit**

```powershell
git add himawari_ir_toolkit/satellite_providers.py himawari_ir_toolkit/draw_ir_fulldisk.py himawari_ir_toolkit/tests/test_satellite_providers.py himawari_ir_toolkit/tests/test_download_progress.py
git commit -m "feat: validate GOES archive dates before access"
```

### Task 3: Add Four-Satellite GUI Selection and Date Clamping

**Files:**
- Modify: `himawari_ir_toolkit/himawari_gui.py`
- Test: `himawari_ir_toolkit/tests/test_gui_threading.py`

- [ ] **Step 1: Write failing GUI behavior tests**

```python
from datetime import date


def test_platform_values_use_historical_label(self):
    app = make_fake_gui(platform="Himawari-9")
    self.assertEqual(
        app.platform_combo.values,
        ("Himawari-9", "GOES-16", "GOES-17（历史）", "GOES-18", "GOES-19"),
    )


def test_switching_to_goes17_clamps_date_to_archive_start(self):
    app = make_fake_gui(platform="Himawari-9", date="2024-08-01")
    app.platform_var.value = "GOES-17"
    HimawariGUI._on_platform_change(app, None)
    self.assertEqual(app.date_var.value, "2018-12-04")


def test_switching_to_goes16_clamps_future_date_to_archive_end(self):
    app = make_fake_gui(platform="GOES-19", date="2025-05-01")
    app.platform_var.value = "GOES-16"
    HimawariGUI._on_platform_change(app, None)
    self.assertEqual(app.date_var.value, "2025-04-06")
```

- [ ] **Step 2: Run GUI tests and verify they fail**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_gui_threading.TestHistoricalSatelliteGUI -v
```

Expected: fail because the GUI still exposes only the existing platform list and does not clamp dates.

- [ ] **Step 3: Implement provider-aware label and date synchronization**

Use stable identifiers internally and labels only for display. When the current date is outside a selected platform window, set it to the nearest inclusive bound:

```python
def _clamp_platform_date(self, platform):
    value = date.fromisoformat(self.date_var.get())
    start, end = get_archive_window(platform)
    if value < start:
        value = start
    if end is not None and value > end:
        value = end
    self.date_var.set(value.isoformat())
```

Update platform combo values to include `GOES-16`, `GOES-17（历史）`, `GOES-18`, `GOES-19`, but map the displayed historical label back to the stable `GOES-17` identifier before provider calls. Prefer storing stable identifiers in the combo values and using a separate display mapping if the current fake controls cannot support display/value pairs.

When the platform changes, clamp the date before rebuilding time options and preserve the existing hour/minute rules. `GOES-17（历史）` must never be passed to S3 or `draw_ir_fulldisk` as the platform identifier.

- [ ] **Step 4: Run GUI tests and full regression**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_gui_threading.TestHistoricalSatelliteGUI -v
python -m unittest discover -s himawari_ir_toolkit/tests -t . -v
```

Expected: historical label and date-clamping tests pass; all existing task invalidation and GOES tests remain green.

- [ ] **Step 5: Commit**

```powershell
git add himawari_ir_toolkit/himawari_gui.py himawari_ir_toolkit/tests/test_gui_threading.py
git commit -m "feat: constrain GUI dates by GOES archive window"
```

### Task 4: Run Product Acceptance and Update Monitor Scope

**Files:**
- Modify only if a concrete test or smoke failure requires it: relevant provider, drawing, GUI, or test file.

- [ ] **Step 1: Run complete local verification**

```powershell
python -m unittest discover -s himawari_ir_toolkit/tests -t . -v
git diff --check
```

Expected: all tests pass with no whitespace errors.

- [ ] **Step 2: Verify local API boundaries without network**

```powershell
python -c "from datetime import datetime; from himawari_ir_toolkit.satellite_providers import validate_archive_date; validate_archive_date('GOES-17', datetime(2023,1,10)); print('boundary OK')"
python -c "from himawari_ir_toolkit.draw_ir_fulldisk import build_parser; print(build_parser().parse_args(['--platform','GOES-17','--time','2023-01-10T09:00:00']))"
```

Expected: boundary validation succeeds and CLI retains stable platform identifier `GOES-17`.

- [ ] **Step 3: Run real smoke tests when NOAA S3 is available**

For one date inside each historical window, use IR B14 first:

```powershell
python -c "from datetime import datetime; from himawari_ir_toolkit.satellite_providers import load_goes_scene; print(load_goes_scene('GOES-16', datetime(2024,8,1,9,0), 'IR', 'B14').data.shape)"
python -c "from datetime import datetime; from himawari_ir_toolkit.satellite_providers import load_goes_scene; print(load_goes_scene('GOES-17', datetime(2022,8,1,9,0), 'IR', 'B14').data.shape)"
```

Expected: each exact slot either loads a valid scene or produces the existing actionable no-scan error; do not substitute a nearby scan. The current sandbox may block these requests, which must be reported rather than hidden.

- [ ] **Step 4: Keep UI polish separate**

Do not add animations, color redesign, layout changes, or transition effects in this plan. Start a new design/spec cycle after archive-date acceptance.

- [ ] **Step 5: Commit only concrete acceptance fixes**

```powershell
git status --short
git diff --check
```

Do not commit generated build/release output or an empty commit.

## Self-Review

- Spec coverage: Task 1 covers four identifiers, labels, buckets, and archive bounds; Task 2 covers inclusive API validation before S3; Task 3 covers GUI labels and clamping; Task 4 covers regression, smoke boundaries, and the explicit UI-polish deferral.
- Scope: No automatic satellite switching, RGB, regional domains, animation, or new renderer branches are included.
- Consistency: Provider identifiers remain `GOES-16`/`GOES-17`/`GOES-18`/`GOES-19`; only the GUI display label uses `GOES-17（历史）`.
- No unresolved placeholders or unspecified acceptance commands remain.

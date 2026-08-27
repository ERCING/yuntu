# Target 机动观测经纬网格与内侧标签（正确投影）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Target（机动观测）区域装饰模式下，用 Cartopy CRS 变换正确绘制 1° 经纬网格，并将经纬度标签绘制到图像内侧。

**Architecture:** 在 `draw_ir_fulldisk.py` 内新增两个小型帮助函数：一个负责从投影坐标范围反算可见经纬范围，另一个负责生成/绘制网格线与内侧标签；Target + decorations 分支调用该函数替换原先 tan 近似实现。

**Tech Stack:** Python, numpy, matplotlib, cartopy

---

## File Map

**Modify**
- `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py`

**Create**
- `e:/ai/fldk/himawari_ir_toolkit/tests/test_target_graticule.py`
- `e:/ai/fldk/himawari_ir_toolkit/tests/__init__.py`

---

### Task 1: 添加可测试的几何/标签选择工具函数

**Files:**
- Modify: `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py`
- Test: `e:/ai/fldk/himawari_ir_toolkit/tests/test_target_graticule.py`

- [ ] **Step 1: 新增 tests 目录与 unittest 骨架**

创建 `himawari_ir_toolkit/tests/__init__.py`（空文件）。

创建 `himawari_ir_toolkit/tests/test_target_graticule.py`：

```python
import math
import unittest

import numpy as np

from draw_ir_fulldisk import _split_valid_segments, _pick_nearest_point_index


class TestTargetGraticuleHelpers(unittest.TestCase):
    def test_split_valid_segments_splits_on_invalid(self):
        x = np.array([0, 1, math.nan, 3, 4, math.nan, 6], dtype=float)
        y = np.array([0, 1, math.nan, 3, 4, math.nan, 6], dtype=float)
        segs = _split_valid_segments(x, y)
        self.assertEqual(len(segs), 3)
        self.assertTrue(np.allclose(segs[0][0], [0, 1]))
        self.assertTrue(np.allclose(segs[1][0], [3, 4]))
        self.assertTrue(np.allclose(segs[2][0], [6]))

    def test_pick_nearest_point_index_works(self):
        x = np.array([0, 2, 5, 9], dtype=float)
        idx = _pick_nearest_point_index(x, target=6.1)
        self.assertEqual(idx, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确保失败（当前函数未实现）**

Run:

```bash
python -m unittest -v himawari_ir_toolkit.tests.test_target_graticule
```

Expected: FAIL，提示 `ImportError` 或找不到 `_split_valid_segments` / `_pick_nearest_point_index`。

- [ ] **Step 3: 在 draw_ir_fulldisk.py 中实现两个工具函数**

在 `draw_ir_fulldisk.py` 中新增：

```python
import numpy as np


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
```

- [ ] **Step 4: 再跑测试，确保通过**

Run:

```bash
python -m unittest -v himawari_ir_toolkit.tests.test_target_graticule
```

Expected: PASS

- [ ] **Step 5: 提交（可选）**

如果需要提交：

```bash
git add himawari_ir_toolkit/draw_ir_fulldisk.py himawari_ir_toolkit/tests
git commit -m "test: add helper tests for target graticule labels"
```

---

### Task 2: 实现正确投影的 Target 网格线与内侧标签绘制

**Files:**
- Modify: `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py`
- Test: `e:/ai/fldk/himawari_ir_toolkit/tests/test_target_graticule.py`

- [ ] **Step 1: 追加一个轻量的 cartopy 变换冒烟测试（不联网）**

在 `test_target_graticule.py` 追加：

```python
import cartopy.crs as ccrs

from draw_ir_fulldisk import compute_target_lonlat_bounds


class TestTargetGraticuleCartopy(unittest.TestCase):
    def test_compute_target_lonlat_bounds_returns_reasonable_values(self):
        geos = ccrs.Geostationary(central_longitude=175.0, satellite_height=35785863.0, sweep_axis="x")
        extent = (-1_000_000.0, 1_000_000.0, -1_000_000.0, 1_000_000.0)
        b = compute_target_lonlat_bounds(geos, extent, samples=200)
        self.assertIsNotNone(b)
        lon_min, lon_max, lat_min, lat_max = b
        self.assertTrue(-180.0 <= lon_min <= 180.0)
        self.assertTrue(-180.0 <= lon_max <= 180.0)
        self.assertTrue(-90.0 <= lat_min <= 90.0)
        self.assertTrue(-90.0 <= lat_max <= 90.0)
        self.assertTrue(lon_min < lon_max)
        self.assertTrue(lat_min < lat_max)
```

- [ ] **Step 2: 跑测试，确保失败（compute_target_lonlat_bounds 未实现）**

Run:

```bash
python -m unittest -v himawari_ir_toolkit.tests.test_target_graticule
```

Expected: FAIL，提示 `compute_target_lonlat_bounds` 不存在。

- [ ] **Step 3: 实现 compute_target_lonlat_bounds**

在 `draw_ir_fulldisk.py` 中实现：

```python
import numpy as np
import cartopy.crs as ccrs


def compute_target_lonlat_bounds(geos_crs: ccrs.CRS, extent: tuple[float, float, float, float], samples: int = 300):
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

    lon = lon[m]
    lat = lat[m]
    lon_min = float(np.nanmin(lon))
    lon_max = float(np.nanmax(lon))
    lat_min = float(np.nanmin(lat))
    lat_max = float(np.nanmax(lat))
    if not (lon_min < lon_max and lat_min < lat_max):
        return None
    return lon_min, lon_max, lat_min, lat_max
```

- [ ] **Step 4: 实现 draw_target_graticule_and_labels（1°网格、内侧标签）**

在 `draw_ir_fulldisk.py` 中实现：

```python
def draw_target_graticule_and_labels(ax, geos_crs, extent, step_deg: float = 1.0, npts: int = 200):
    bounds = compute_target_lonlat_bounds(geos_crs, extent, samples=300)
    if bounds is None:
        return
    lon_min, lon_max, lat_min, lat_max = bounds

    lon_ticks = np.arange(np.ceil(lon_min), np.floor(lon_max) + 1e-6, step_deg)
    lat_ticks = np.arange(np.ceil(lat_min), np.floor(lat_max) + 1e-6, step_deg)

    x_min, x_max, y_min, y_max = extent
    dx = (x_max - x_min) * 0.012
    dy = (y_max - y_min) * 0.012
    x_target = x_min + dx
    y_target = y_min + dy

    pc = ccrs.PlateCarree()

    line_style = dict(color="gray", linewidth=0.25, linestyle="--", alpha=0.35, zorder=3)
    label_bbox = dict(facecolor="white", edgecolor="none", alpha=0.45, boxstyle="square,pad=0.12")

    lat_line = np.linspace(lat_min, lat_max, npts)
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
            idx = _pick_nearest_point_index(xv, x_target)
            if np.isfinite(xv[idx]) and np.isfinite(yv[idx]):
                ax.text(
                    float(xv[idx]),
                    float(yv[idx]),
                    f"{int(round(lo))}°E",
                    transform=geos_crs,
                    fontsize=6,
                    color="black",
                    ha="left",
                    va="center",
                    zorder=4,
                    bbox=label_bbox,
                )

    lon_line = np.linspace(lon_min, lon_max, npts)
    for la in lat_ticks:
        lat_line2 = np.full_like(lon_line, la)
        pts = geos_crs.transform_points(pc, lon_line, lat_line2)
        x = pts[:, 0]
        y = pts[:, 1]
        for xs, ys in _split_valid_segments(x, y):
            ax.plot(xs, ys, transform=geos_crs, **line_style)

        m = np.isfinite(x) & np.isfinite(y)
        if np.any(m):
            xv = x[m]
            yv = y[m]
            idx = _pick_nearest_point_index(yv, y_target)
            if np.isfinite(xv[idx]) and np.isfinite(yv[idx]):
                ax.text(
                    float(xv[idx]),
                    float(yv[idx]),
                    f"{int(round(la))}°N",
                    transform=geos_crs,
                    fontsize=6,
                    color="black",
                    ha="center",
                    va="bottom",
                    zorder=4,
                    bbox=label_bbox,
                )
```

- [ ] **Step 5: 将 Target + decorations 分支切换到新实现**

在 `draw_ir_fulldisk.py` 中，定位 “添加网格线” 逻辑块，替换 Target 分支的现有刻度/网格线实现为：

```python
if add_decorations:
    if region_full == "Target":
        draw_target_graticule_and_labels(ax, geos_crs, src_extent, step_deg=1.0)
    else:
        gl = ax.gridlines(draw_labels=True, linestyle="--", linewidth=0.3, color="gray", alpha=0.5)
        gl.top_labels = False
        gl.right_labels = False
        gl.left_labels = True
        gl.bottom_labels = True
        gl.xlabel_style = {"size": 5, "color": "black"}
        gl.ylabel_style = {"size": 5, "color": "black"}
else:
    gl = ax.gridlines(draw_labels=False, linestyle="--", linewidth=0.3, color="gray", alpha=0.5)
```

- [ ] **Step 6: 跑单测，确保通过**

Run:

```bash
python -m unittest -v himawari_ir_toolkit.tests.test_target_graticule
```

Expected: PASS

- [ ] **Step 7: 提交（可选）**

```bash
git add himawari_ir_toolkit/draw_ir_fulldisk.py himawari_ir_toolkit/tests
git commit -m "feat: draw correct target graticule labels inside image"
```

---

### Task 3: 端到端验证（实际出一张 Target 图）

**Files:**
- Modify: `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py`

- [ ] **Step 1: 运行 Target 绘制命令（需要联网下载数据）**

Run:

```bash
python himawari_ir_toolkit/draw_ir_fulldisk.py --time "2026-07-27T09:00:00" --data-type IR --band B14 --scheme IR-WK --region T --dpi 150 --decorations
```

Expected:
- 命令正常结束（exit code 0）
- 输出 png 在 `himawari_ir_toolkit/data/` 下生成
- Target 图中经纬网格线存在、标签在图像内侧，且与海岸线位置关系合理

- [ ] **Step 2: 对比旧图（可选）**

再生成一张全圆盘图，确认非 Target 行为不变：

```bash
python himawari_ir_toolkit/draw_ir_fulldisk.py --time "2026-07-27T09:00:00" --data-type IR --band B14 --scheme IR-WK --region F --dpi 150 --decorations
```

- [ ] **Step 3: 如有必要，微调样式参数**

可调整参数（保持目标：不抢画面、可读）：
- `line_style` 的 `alpha/linewidth`
- `label_bbox` 的 `alpha/pad`
- `fontsize`（6 -> 7）

---

## Self-Review Checklist

- Spec coverage：Target+decorations 下经纬网格与内侧标签均已由新函数负责；非 Target 不变
- Placeholder scan：无 TODO/TBD
- Consistency：函数命名与测试导入一致；step_deg 固定 1°


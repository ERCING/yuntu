# Target 机动观测经纬网格与内侧标签（正确投影）设计

## 背景

现有 Target（机动观测）区域的经纬度标注使用简化的正切近似将经纬度映射到 Geostationary 投影坐标，用于生成刻度与网格线。这种方式在 Geostationary 投影下不保证正确，容易在大视角/边缘出现偏差，导致经纬度标注不可信。

用户诉求：
- Target 区域经纬度网格与标签必须正确
- 标签需要绘制在图像内侧（非轴外/非画布外）
- 网格密度固定为 1°
- 视觉需要更美观：网格线不抢画面、标签可读但克制

## 范围

仅覆盖 `draw_ir_fulldisk.py` 中 Target 区域在装饰模式（`add_decorations=True`）下的经纬度相关绘制逻辑：
- 替换 Target 专用网格/刻度/标签实现
- 非 Target（全圆盘/日本）逻辑保持现状
- 非装饰模式保持现状（默认不绘制标签）

## 目标与非目标

### 目标
- 以 Cartopy CRS 变换为基础正确绘制经纬网格（1°）
- 将经纬度标签绘制在图像内部边缘位置（内侧），并保证清晰可读
- 对不可见区域/变换失败点具备容错（跳过该线/该标签）

### 非目标
- 不对 Target 的中心经度估算逻辑做额外改造（沿用现有 `central_lon` 逻辑）
- 不做复杂的标签避让排版（如自动避让、重叠检测），仅做基础的稀疏放置与边缘对齐

## 设计概述

在 Target + decorations 模式下，采用两步：
1) 用 CRS 变换确定可见经纬范围（lon/lat bounds）
2) 以固定 1° 间隔生成经纬线，并用 `PlateCarree -> Geostationary` 正向变换得到投影坐标 polyline，使用 `ax.plot` 绘制；标签在 “靠近左边界/下边界的内侧” 放置

### 关键数据与坐标系

- 数据绘制坐标系：`geos_crs = ccrs.Geostationary(central_longitude=central_lon, satellite_height=h, sweep_axis="x")`
- 经纬坐标系：`ccrs.PlateCarree()`
- 数据在投影坐标系下的可视范围：`src_extent = (x_min, x_max, y_min, y_max)`，其中 x/y 为米

### 1) 可见范围估算（lon/lat bounds）

使用数据边界采样点进行反变换，得到可视边界对应的经纬度范围：
- 在四条边界上各采样 N 个点（例如 N=300）
  - Top: (x in [x_min,x_max], y=y_max)
  - Bottom: (x in [x_min,x_max], y=y_min)
  - Left: (x=x_min, y in [y_min,y_max])
  - Right: (x=x_max, y in [y_min,y_max])
- 使用 `PlateCarree().transform_points(geos_crs, xs, ys)` 得到 (lon, lat)
- 过滤无效点（nan/inf 或超出经纬范围的异常点），得到：
  - `lon_min, lon_max, lat_min, lat_max`

边界情况：
- 如果有效点不足（例如全部不可见），则禁用网格与标签（仅显示云图与海岸线）

### 2) 网格线生成与绘制（1°）

生成 1° 间隔的经纬线：
- 经度线：`lon = k`，`lat` 取 `[lat_min, lat_max]` 的等间隔序列（例如 200 点）
- 纬度线：`lat = k`，`lon` 取 `[lon_min, lon_max]` 的等间隔序列（例如 200 点）

对每条线：
- 用 `geos_crs.transform_points(PlateCarree(), lons, lats)` 得到 (x, y)
- 过滤无效点，并把连续有效段用 `ax.plot(x_seg, y_seg, ...)` 绘制

样式（美观优先）：
- 线宽：0.25
- 颜色：灰色
- 透明度：0.35
- 虚线：`"--"`

### 3) 内侧标签放置策略

避免 axis tick + formatter 体系，直接在数据坐标（投影坐标）上放置文本。

定义内侧边距：
- `dx = (x_max - x_min) * 0.012`
- `dy = (y_max - y_min) * 0.012`

放置规则：
- 经度标签：放在接近左边界的内侧 `x_target = x_min + dx`
  - 在该经度线 polyline 上找与 `x_target` 最近且有效的点 (x*, y*)
  - 在 (x*, y*) 放置 `"{lon}°E"`，水平对齐 left，垂直居中
- 纬度标签：放在接近下边界的内侧 `y_target = y_min + dy`
  - 在该纬度线 polyline 上找与 `y_target` 最近且有效的点 (x*, y*)
  - 在 (x*, y*) 放置 `"{lat}°N"`，水平居中，垂直对齐 bottom

文本样式（可读且克制）：
- 字号：6（必要时可调到 7）
- 颜色：黑色（或深灰）
- 背景：使用半透明白底 bbox（alpha≈0.45，pad≈0.12）以提升在云图上的可读性

降级策略：
- 如果该线找不到足够接近的点（距离阈值过大），跳过该标签
- 为减少拥挤：标签可只对每 2° 标注一次，但本期按用户要求固定 1° 全部标注；如拥挤再回退策略

## 与现有代码的集成点

文件：[draw_ir_fulldisk.py](file:///e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py)
- 替换 Target + decorations 分支中手动刻度与 `axvline/axhline` 的逻辑（现位置约 L258-L281）
- 保留非 Target 分支的 `ax.gridlines(draw_labels=True...)` 不变

建议结构：
- 新增内部帮助函数（同文件内）：
  - `compute_target_lonlat_bounds(geos_crs, src_extent) -> (lon_min, lon_max, lat_min, lat_max) | None`
  - `draw_target_graticule_and_labels(ax, geos_crs, src_extent, step_deg=1)`

## 验收标准

- Target 区域网格与地理要素（海岸线/国界）对齐合理，无明显偏移
- 标签位于图像内侧，且不溢出画布、不跑到色标区域
- 网格线足够淡，不抢主体云图对比
- 变换失败/不可见情况下不会报错，最多缺失部分线或自动降级为无网格


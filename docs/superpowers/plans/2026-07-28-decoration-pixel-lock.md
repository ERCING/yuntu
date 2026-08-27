# Decoration Pixel Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让顶部信息栏和右侧色标按固定像素目标渲染，从而与主图大小解耦，并在 FLDK 与 Target 上都保持稳定可读的屏幕观感。

**Architecture:** 仅修改 `himawari_ir_toolkit/draw_ir_fulldisk.py` 的装饰布局计算逻辑。把当前按区域硬编码的字号/色标宽度改成统一的像素锁定度量函数，再在装饰分支里用这些度量替换写死常量。测试覆盖新度量函数输出，确保不再退回“FLDK 写死更大字号”的做法。

**Tech Stack:** Python, matplotlib, cartopy, unittest

---

## File Map

**Modify**
- `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py`
- `e:/ai/fldk/himawari_ir_toolkit/tests/test_target_graticule.py`

**Verify**
- `e:/ai/fldk/himawari_ir_toolkit/data/`

---

### Task 1: 用测试锁定像素布局度量函数

**Files:**
- Modify: `e:/ai/fldk/himawari_ir_toolkit/tests/test_target_graticule.py`
- Modify: `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py`

- [ ] **Step 1: 写一个失败测试，覆盖像素锁定布局输出**

把现有 `get_decoration_font_sizes` 的测试替换为：

```python
from himawari_ir_toolkit.draw_ir_fulldisk import get_decoration_layout_metrics


class TestDecorationLayoutMetrics(unittest.TestCase):
    def test_layout_metrics_follow_pixel_targets_for_large_figure(self):
        m = get_decoration_layout_metrics(region_full="FLDK", fig_w=36.7, fig_h=36.7, dpi=150)
        self.assertEqual(m["info_fontsize"], 13)
        self.assertEqual(m["cbar_tick_size"], 9)
        self.assertAlmostEqual(m["header_gap_fig"], 14 / (36.7 * 150), places=6)
        self.assertAlmostEqual(m["cbar_gap"], 10 / (36.7 * 150), places=6)
        self.assertAlmostEqual(m["cbar_width"], 18 / (36.7 * 150), places=6)

    def test_layout_metrics_clamp_small_figure_sizes(self):
        m = get_decoration_layout_metrics(region_full="Target", fig_w=3.45, fig_h=3.33, dpi=150)
        self.assertEqual(m["info_fontsize"], 13)
        self.assertEqual(m["cbar_tick_size"], 9)
        self.assertGreaterEqual(m["cbar_width"], 0.010)
```

- [ ] **Step 2: 运行测试，确认失败**

Run:

```bash
python -m unittest -v himawari_ir_toolkit.tests.test_target_graticule
```

Expected: FAIL，提示 `get_decoration_layout_metrics` 未定义或旧测试导入失败。

- [ ] **Step 3: 在绘图模块中实现像素锁定布局函数**

在 `draw_ir_fulldisk.py` 里新增：

```python
def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def get_decoration_layout_metrics(region_full: str, fig_w: float, fig_h: float, dpi: int) -> dict[str, float]:
    fig_w_px = fig_w * dpi
    fig_h_px = fig_h * dpi

    header_font_px = 28
    header_gap_px = 14
    cbar_width_px = 18
    cbar_gap_px = 10
    cbar_tick_px = 18

    info_fontsize = _clamp(round(header_font_px * 72 / dpi), 11, 22)
    cbar_tick_size = _clamp(round(cbar_tick_px * 72 / dpi), 9, 16)

    return {
        "info_fontsize": info_fontsize,
        "cbar_tick_size": cbar_tick_size,
        "header_gap_fig": header_gap_px / fig_h_px,
        "cbar_gap": cbar_gap_px / fig_w_px,
        "cbar_width": max(0.010, cbar_width_px / fig_w_px),
    }
```

- [ ] **Step 4: 跑测试，确认新函数通过**

Run:

```bash
python -m unittest -v himawari_ir_toolkit.tests.test_target_graticule
```

Expected: PASS

---

### Task 2: 在装饰模式中接入统一布局度量

**Files:**
- Modify: `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py:453-486`

- [ ] **Step 1: 用布局度量替换写死常量**

把当前装饰分支中的：

```python
ax_pos = ax.get_position()
cbar_gap = 0.008
cbar_width = 0.014
cbar_x = ax_pos.x1 + cbar_gap
cbar_y = ax_pos.y0
cbar_h = ax_pos.height
header_y = min(0.99, ax_pos.y1 + 0.012)
info_fontsize, cbar_tick_size = get_decoration_font_sizes(region_full, fig_w, fig_h)
```

替换为：

```python
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
```

- [ ] **Step 2: 删除旧的按区域硬编码字号函数**

删除：

```python
def get_decoration_font_sizes(region_full: str, fig_w: float, fig_h: float) -> tuple[int, int]:
    if region_full == "FLDK":
        return 9, 6
    if fig_w <= 6 or fig_h <= 6:
        return 6, 4
    return 7, 5
```

- [ ] **Step 3: 再跑一次测试**

Run:

```bash
python -m unittest -v himawari_ir_toolkit.tests.test_target_graticule
```

Expected: PASS

---

### Task 3: 端到端出图验证像素锁定效果

**Files:**
- Modify: `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py`

- [ ] **Step 1: 重新生成 FLDK 图**

Run:

```bash
python e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py --time "2025-07-24T06:00:00" --data-type IR --band B14 --scheme IR-CC --region F --dpi 150 --decorations
```

Expected:
- 顶部 `标题 / 时间 / dmax-dmin` 明显大于当前版本
- 右侧色标宽度不再细得像针
- 色标顶部/底部与主图严格对齐

- [ ] **Step 2: 重新生成 Target 图**

Run:

```bash
python e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py --time "2026-07-27T09:00:00" --data-type IR --band B14 --scheme IR-WK --region T --dpi 150 --decorations
```

Expected:
- 顶部信息栏不重叠
- 色标宽度较之前更稳定
- 主图范围和裁切不发生变化

- [ ] **Step 3: 收集诊断**

Run: 使用 `GetDiagnostics`

Expected: 无新报错

---

## Self-Review Checklist

- Spec coverage：覆盖字号、顶部间距、色标宽度与间距、色标刻度字号
- Placeholder scan：无 TODO/TBD
- Consistency：所有装饰布局统一由 `get_decoration_layout_metrics()` 输出，不再混用旧硬编码函数

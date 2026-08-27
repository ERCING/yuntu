# FLDK 顶部字号自适应 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 FLDK 图的顶部信息栏在视觉上与 Target 图接近，同时保持现有布局、字重和对齐方式不变。

**Architecture:** 仅修改 `draw_ir_fulldisk.py` 中顶部信息栏字号与色标刻度字号的计算方式。通过区域/图幅驱动的自适应字号，让 FLDK 自动放大一档，Target 保持当前观感，避免全局固定字号导致小图拥挤。

**Tech Stack:** Python, matplotlib, cartopy

---

## File Map

**Modify**
- `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py`

**Reuse for verification**
- `e:/ai/fldk/himawari_ir_toolkit/tests/test_target_graticule.py`

---

### Task 1: 提取顶部信息栏字号策略

**Files:**
- Modify: `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py`
- Test: `e:/ai/fldk/himawari_ir_toolkit/tests/test_target_graticule.py`

- [ ] **Step 1: 先写一个失败的字号策略测试**

在 `test_target_graticule.py` 里追加：

```python
from himawari_ir_toolkit.draw_ir_fulldisk import get_decoration_font_sizes


class TestDecorationFontSizes(unittest.TestCase):
    def test_fldk_gets_larger_header_size_than_target(self):
        header_f, cbar_f = get_decoration_font_sizes(region_full="FLDK", fig_w=36.7, fig_h=36.7)
        header_t, cbar_t = get_decoration_font_sizes(region_full="Target", fig_w=3.45, fig_h=3.33)
        self.assertGreater(header_f, header_t)
        self.assertGreaterEqual(cbar_f, cbar_t)
```

- [ ] **Step 2: 运行测试，确认失败**

Run:

```bash
python -m unittest -v himawari_ir_toolkit.tests.test_target_graticule
```

Expected: FAIL，提示 `get_decoration_font_sizes` 未定义。

- [ ] **Step 3: 在 `draw_ir_fulldisk.py` 中实现字号策略函数**

新增函数：

```python
def get_decoration_font_sizes(region_full: str, fig_w: float, fig_h: float) -> tuple[int, int]:
    if region_full == "FLDK":
        return 9, 6
    if fig_w <= 6 or fig_h <= 6:
        return 6, 4
    return 7, 5
```

- [ ] **Step 4: 在绘图逻辑里接入该函数**

把原来的：

```python
info_fontsize = 6
...
cbar.ax.tick_params(labelsize=4)
```

替换为：

```python
info_fontsize, cbar_tick_size = get_decoration_font_sizes(region_full, fig_w, fig_h)
...
cbar.ax.tick_params(labelsize=cbar_tick_size)
```

- [ ] **Step 5: 跑测试确认通过**

Run:

```bash
python -m unittest -v himawari_ir_toolkit.tests.test_target_graticule
```

Expected: PASS

---

### Task 2: 端到端验证 FLDK / Target 视觉一致性

**Files:**
- Modify: `e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py`

- [ ] **Step 1: 重新生成 FLDK 图**

Run:

```bash
python e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py --time "2025-07-24T06:00:00" --data-type IR --band B14 --scheme IR-CC --region F --dpi 150 --decorations
```

Expected:
- 顶部三段文字明显比当前 FLDK 更大
- 右侧色标与主图仍然严格对齐
- 底部仍无文字

- [ ] **Step 2: 重新生成 Target 图**

Run:

```bash
python e:/ai/fldk/himawari_ir_toolkit/draw_ir_fulldisk.py --time "2026-07-27T09:00:00" --data-type IR --band B14 --scheme IR-WK --region T --dpi 150 --decorations
```

Expected:
- Target 顶部文字观感基本不变
- 不出现挤压或重叠

- [ ] **Step 3: 如果 FLDK 仍然偏小，微调字号档位**

仅允许改这一段：

```python
if region_full == "FLDK":
    return 10, 6
```

或：

```python
if region_full == "FLDK":
    return 8, 5
```

禁止修改顶部布局结构、文案内容、色标对齐逻辑。

---

## Self-Review Checklist

- Spec coverage：只放大 FLDK 顶部字号，Target 保持当前款式
- Placeholder scan：无 TODO/TBD
- Consistency：字号策略通过单一函数输出，顶部信息栏与色标刻度同步使用


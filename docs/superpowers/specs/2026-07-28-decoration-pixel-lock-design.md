# 顶部信息栏与色标像素锁定设计

## 背景

当前 FLDK 与 Target 都把顶部信息栏和右侧色标作为整张 Matplotlib figure 的一部分输出。虽然 `fontsize`、`cbar_width` 等参数在代码里可以独立设置，但一旦导出为超大 PNG，图片查看器会把整张图按屏幕尺寸缩小显示，导致顶部文字和色标在 FLDK 上显得离谱地小。

用户已经确认的约束：
- 主图尺寸继续按区域决定，不为了文字去缩小 FLDK 主图
- 顶部信息栏保持单行、同字号、同字重、同基线
- 右侧色标顶部/底部必须与主图严格对齐
- 底部不再放置任何文字
- 所有区域继续禁用经纬度标注

本次设计目标不是“继续调大固定字号”，而是让顶部栏和色标的视觉尺寸从主图大小中解耦。

## 范围

仅覆盖 `himawari_ir_toolkit/draw_ir_fulldisk.py` 中装饰模式（`add_decorations=True`）的以下内容：
- 顶部信息栏字号计算
- 顶部信息栏垂直位置
- 右侧色标宽度与间距
- 色标刻度字号

不改动：
- 主图区域的 `figsize`、投影、裁切与数据绘制逻辑
- 顶部信息栏文案结构（仍为 `标题 / 时间 / dmax-dmin`）
- 海岸线、国界线、经纬度标注逻辑

## 目标与非目标

### 目标
- 顶部信息栏的视觉高度由固定像素目标控制，而不是由整张图幅大小控制
- 右侧色标宽度和主图间距由固定像素目标控制
- FLDK 和 Target 共用同一套像素规则，但允许通过上下限避免小图被撑爆
- 保持现有布局结构不变，只改善“看起来太小”的问题

### 非目标
- 不引入新的布局模式或多行标题
- 不做交互式缩放适配
- 不重做 GUI，仅调整导出图片效果

## 设计概述

采用“像素锁定”的装饰布局：
- 顶部信息栏的字号和垂直留白按目标像素值换算成 figure 坐标
- 右侧色标的宽度与间距按目标像素值换算成 figure 坐标
- 主图区仍由 `ax.get_position()` 决定；色标与顶部栏只围绕主图区做像素级附着

这意味着：
- 主图多大都可以
- 顶部栏始终接近固定的屏幕可读高度
- 色标不会因为大图而变成一根很细的针

## 核心参数

定义一组装饰目标像素参数：

- `header_font_px = 28`
- `header_gap_px = 14`
- `cbar_width_px = 18`
- `cbar_gap_px = 10`
- `cbar_tick_px = 18`

并加入上下限，防止极端图幅下过小或过大：

- `header_fontsize_pt` 限制在 `11 ~ 22`
- `cbar_ticksize_pt` 限制在 `9 ~ 16`
- `cbar_width_fig` 至少保证 `0.010`

说明：
- 像素目标是为了“屏幕查看观感”而设定
- Matplotlib 的文字接口使用 pt，因此需要先把像素换算为 pt
- 色标宽度和间距最终需要换算成 figure 坐标（0-1）

## 换算规则

### 1) 字号换算

已知：
- `dpi`
- figure 总像素高度 `fig_h_px = fig_h * dpi`

将目标像素高度换算为 pt：

- `fontsize_pt = header_font_px * 72 / dpi`
- `ticksize_pt = cbar_tick_px * 72 / dpi`

再施加上下限：

- `info_fontsize = clamp(round(fontsize_pt), 11, 22)`
- `cbar_tick_size = clamp(round(ticksize_pt), 9, 16)`

这样文字大小只取决于导出 dpi 和目标像素值，不取决于 FLDK 主图到底有多大。

### 2) 顶部栏垂直位置换算

将顶部留白像素换算为 figure 归一化坐标：

- `header_gap_fig = header_gap_px / fig_h_px`
- `header_y = min(0.99, ax_pos.y1 + header_gap_fig)`

这样顶部信息栏与主图顶部之间保持稳定的像素间距。

### 3) 色标宽度与间距换算

已知：
- figure 总像素宽度 `fig_w_px = fig_w * dpi`

换算：

- `cbar_gap = cbar_gap_px / fig_w_px`
- `cbar_width = max(0.010, cbar_width_px / fig_w_px)`
- `cbar_x = ax_pos.x1 + cbar_gap`
- `cbar_y = ax_pos.y0`
- `cbar_h = ax_pos.height`

这样色标宽度与主图间距保持稳定的像素观感，同时顶部/底部仍与主图严格对齐。

## 代码结构

建议把当前的 `get_decoration_font_sizes()` 扩展为统一的装饰布局计算函数，例如：

```python
def get_decoration_layout_metrics(region_full: str, fig_w: float, fig_h: float, dpi: int) -> dict[str, float]:
    ...
```

返回内容至少包括：
- `info_fontsize`
- `cbar_tick_size`
- `header_gap_fig`
- `cbar_gap`
- `cbar_width`

接入点仍在 `draw_ir_fulldisk()` 的装饰模式分支内，替换当前写死的：
- `cbar_gap = 0.008`
- `cbar_width = 0.014`
- `header_y = ax_pos.y1 + 0.012`
- 固定 `info_fontsize`
- 固定 `cbar_tick_size`

## 验收标准

- FLDK 导出后，顶部 `标题 / 时间 / dmax-dmin` 在普通图片查看器缩放到屏幕时仍然清晰可读
- Target 的顶部信息栏不出现拥挤、重叠、越界
- 右侧色标仍与主图顶部/底部严格对齐
- 色标视觉宽度明显优于当前“细得像针”的效果
- 不改变现有主图范围、裁切、投影、海岸线和国界线效果

## 风险与降级

风险：
- 不同查看器的默认缩放策略不同，因此“可读”仍有一定主观性
- 某些极端 dpi 组合下，纯像素换算可能使字号略偏大或偏小

降级策略：
- 若首次效果仍偏小，只调 `header_font_px` 与 `cbar_tick_px`
- 若色标偏宽或偏窄，只调 `cbar_width_px`
- 不再回退到“按区域手写不同固定字号”的方式

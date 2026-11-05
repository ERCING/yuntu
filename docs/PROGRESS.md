# 当前进度与交接

> 快照时间：2026-11-05 11:40（UTC+8）
> 基线提交：`4de852d`（工作区除下列未跟踪文件外是干净的）

这份文档记录"做到哪了、验证过什么、下一步该做什么"，用于中断后继续，不依赖对话记录。

---

## 一、已完成（两个提交）

### `f970904` — 修复 UI 队列假死、深色主题泄漏、装饰字号区域特例

| 问题 | 修法 | 影响面 |
|---|---|---|
| UI 队列假死 | `_process_ui_queue` 改 `get_nowait` + `queue.Empty`，逐回调 `try/except`，续排与留痕本身也容错 | 后端回调抛异常不再让 UI 永久失联 |
| 深色主题阴阳脸 | 状态色与错误对话框改走主题令牌 `_pal()`；3 处 disabled 前景改 `p['text_subtle']`；切主题后按最后状态种类重刷 | 深色主题下不再残留浅色 |
| 装饰字号区域特例 | 删掉 `if region_full == "FLDK": 35/35` 硬编码，字号只由画布像素与 dpi 决定 | 全圆盘标题 **35pt → 20pt**、色标刻度 **35 → 14pt**；GOES 与 Himawari 同尺寸出图一致 |

该提交同时纳入了工作区里此前一直未提交的**双主题/响应式 UI 重写**（1142 行），未改动其设计意图。

### `4de852d` — 关窗统一走 `_on_close`

原先点右上角关闭会被 Tk 直接销毁，实测有三层问题叠加：

| 层 | 现象 | 根因 |
|---|---|---|
| 1 | `bgerror ... _process_ui_queue` | UI 泵 after 未存 id |
| 2 | `bgerror ... idle_draw` | matplotlib TkAgg 的 `after_idle` 重绘 |
| 3 | **mainloop 不返回、进程残留** | 只 `destroy()` 不 `quit()`，且处在 after 回调中 |
| 附带 | `bgerror ... _refresh_responsive` | 首帧 `after(0, ...)` 未存 id |

对应改动：`WM_DELETE_WINDOW → _on_close`（有在飞任务先 `askyesno` 确认）、`_cancel_pending_callbacks()`（5 处 after）、`_cancel_matplotlib_callbacks()`（`_idle_draw_id` / `_event_loop_id`）、关窗次序改为 取消回调 → `quit()` → `destroy()`、`_set_draw_button_state` 无论任务是否失效都清 `_draw_in_flight`。

---

## 二、验证状态

| 项 | 结果 |
|---|---|
| 全量测试 | **115 个用例通过**，运行期无任何 `bgerror`（基线是 109 个） |
| 真实 Tk 冒烟（独立脚本，模拟点右上角关闭） | 退出码 `0`，`mainloop` 正常返回，stderr 干净；修复前为 mainloop 不返回 + 进程残留 + bgerror |
| CLI `--list` | 正常（退出码 0） |
| 五模块 import | 全部通过 |

**测试环境事实（重要，别再踩）**
- `.venv` 里**没有 pytest**，测试是 `unittest` 风格。用：
  `.\.venv\Scripts\python.exe -m unittest discover -s himawari_ir_toolkit\tests -t .`
- PowerShell 里给 native 命令加 `2>&1`，unittest 写 stderr 会被判 `NativeCommandError`，退出码不可信；要判成败请重定向到文件并单独看 `$LASTEXITCODE`。
- Python 3.13.5 / matplotlib 3.11.1 / cartopy 0.25.0 / pycontrails 0.63.3 / s3fs 2026.7.0。

**未验证（必须人工）**
- 界面观感：本会话的模型无图像输入能力，看不了 `.tmp_ui_*.png`，也无法联网出图。深色主题、错误弹窗、全圆盘标题变小这三处的实际观感需要人眼过一遍。
- 真实网络下载出图（需要 AWS 访问）。

---

## 三、已知问题清单（尚未修）

按严重度，均已在代码中核实过（不是推测）：

**P0**
1. **右侧图层栏完全未接线** —— 5 个图层复选框、色阶下拉、`vmin`/`vmax`、反转、等值线、3 张队列卡片构造后从未被读取，点了没反应。`current_data` / `current_extent` 只写不读，预览是重开磁盘 PNG 再贴到 Tk canvas 上。
2. **经纬网功能"实现了但从未被调用"** —— `draw_target_graticule_and_labels` 全仓只有测试引用，生产路径无调用者；GUI 的经纬网复选框也没接。2026-07-28 的 spec 把它当作验收项，实际用户看不到。

**P1**
3. 无任何配置持久化：每次重启回到全默认（日期=今天、09:00、Himawari-9）。
4. 引擎无取消机制：关窗时正在下载，`data/` 可能残留写了一半的 PNG（本轮只做到"不静默中断 + 给确认"）。
5. 打包与源码脱节：`build/dist` 的 exe 是 2026-10-25 的，落后于源码；`release/HimawariIRToolkit` 只有一个 `_internal` 目录、**没有 exe**；`build/` 堆了 7 套 PyInstaller 树共约 1.1 GB。
6. 测试里有大量源码字符串/AST 断言，锁定实现细节而非行为；本轮已把其中两处升级为更强契约，其余仍在。

**P2**
7. 文档三套色板互相冲突（`docs/superpowers/*` 与 `.design/*`），`.design` 的三栏 Web 工作台与"不得新增控件"的 spec 结构性对立。
8. 无 README / LICENSE / 架构文档 / 安装说明 / CLI 参考；`himawari_ir_toolkit/` 没有 `__init__.py`（靠命名空间包工作）；根目录 `tests/` 只剩一个孤儿 `.pyc`。
9. 两份 `debug-*.md` 仍未闭环；`ttk-button-contrast` 的埋点日志是 0 字节。
10. `get_decoration_layout_metrics` 的 `cbar_width` 仍保留 `max(0.018, ...)` 下限，对 5500px 宽图实际约 99px，与 18px 像素预算不符（本轮按要求**未动**）。

---

## 四、下一步候选（用户尚未选定）

按用户"一步一步确认"的节奏，中断时待选的是这三项：

1. **先看界面再定控件去留** —— 用户按 `start_gui.bat` 实际跑一遍，确认右侧哪些控件值得接线、哪些直接删。
2. **直接接线/删控件** —— 能接引擎的接（色阶、vmin/vmax、反转），接不了又没价值的删（等值线、图层、队列卡片）。工作量大，适合拆并行子代理。
3. **工程化** —— 补 README + 清 `build/` 旧构建 + 重新打包 + 确认 `release/` 完整。面向"分享给团队"这个既定目标。

---

## 五、环境注意事项

- **工作区 ACL 曾损坏**：本会话开始时 `E:\ai\fldk` 缺少所有者权限，沙箱无法授权写入。已用诊断脚本修复并验证，改动有备份与回滚命令，全部在 `.acl-recovery/`（已加入 `.gitignore`，**不要删**，里面是回滚脚本）。
- 未跟踪文件：`.design/`（设计稿）、`.tmp_shot.py` + `.tmp_ui_*.png`（截图工具与四个尺寸的界面截图），均为用户既有产物，本轮未纳入提交。
- 提交信息较详细，可用 `git show <sha>` 查看每项改动的动机与验证方式。

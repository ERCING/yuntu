# 架构说明

面向要改代码或接手维护的人。描述分层、数据流、关键契约与已踩过的坑。
使用方式与参数见 [`../README.md`](../README.md)；存量问题与计划见 [`PROGRESS.md`](PROGRESS.md)。

---

## 一、分层

```
himawari_gui.py            表现层    Tkinter 单类 HimawariGUI，只管界面与线程调度
      │  只依赖两个符号：draw_ir_fulldisk()、DATA_TYPES
      ▼
draw_ir_fulldisk.py        引擎层    两条渲染管线 + 装饰/布局数学 + CLI 入口
      │
      ▼
satellite_providers.py     数据层    平台配置、S3 发现与下载、Scene 组装与校验
      │
      ▼
satellite_scene.py         模型层    冻结 dataclass：Scene / ProjectionMetadata
mycolor.py                 色阶层    11 套色阶表 → matplotlib Colormap
```

依赖方向是单向的：**表现层不反向被依赖，数据层不认识 matplotlib**。
`satellite_scene.py` 只有两个冻结 dataclass，是整个项目里唯一无副作用的模块。

## 二、数据流

```
用户输入(时间/平台/产品/波段/色阶/区域)
  → 参数校验（数据类型 → 波段 → 色阶 → 区域 → 归档窗口 → 时次槽位）
  → 取数
       Himawari: pycontrails.Himawari.get()      （自行下载+缓存）
       GOES    : s3fs 匿名列举 ABI-L2-CMIPF → 逐文件流式下载带进度 → xarray 打开
  → 组装 Scene
       data: 亮度温度 → °C（−273.15）｜反射率 → %（×100）｜AVG 取双通道逐像元中值
       x_scan_rad / y_scan_rad: 扫描角（弧度，1-D）
       projection: 星下点经度、视点高度、扫描轴、长短半轴
  → 投影坐标      x_proj = perspective_point_height × x_scan_rad
  → 取色阶        my_color_map(scheme) → (cmap, Normalize)
  → imshow        1 数据像素 : 1 图像像素，interpolation='none'
  → 装饰          get_decoration_subplot_adjustments() + get_decoration_layout_metrics()
  → savefig       bbox_inches=None, facecolor='white'
  → 返回          (out_path, data, extent)
```

## 三、两条渲染管线（重要）

引擎里并存两条管线，共享 `imshow + 装饰 + savefig` 中段，但取数与投影来源不同：

| | 管线 B：Himawari（遗留） | 管线 A：GOES（scene 驱动） |
|---|---|---|
| 入口 | `draw_ir_fulldisk()` | `draw_satellite_scene()` |
| 取数 | `pycontrails.datalib.himawari.Himawari` | `load_goes_scene()` |
| 投影 | **硬编码**：星下点 140.7°、高度 35785863.0、sweep 'x' | 由 `Scene.projection` 元数据构造 `ccrs.Geostationary` |
| 装饰 | 完整（标题+时次+极值+色标柱） | 简化（`build_scene_title` + 色标柱） |
| 区域 | 支持 `FLDK` / `Target` | 只有全圆盘 |

> **已知不一致点**：`Scene.region` 恒为 `"F"`，而布局函数历史上按 `"FLDK"` 分支判断。
> 该分支已在 2026-11 移除（字号改为只由像素尺寸与 dpi 决定），但新增任何"按区域"
> 的逻辑时务必记住：Himawari 侧传的是 `"FLDK"`，GOES 侧传的是 `"F"`。

## 四、线程模型

- **每个绘制任务一条 daemon 线程**，无线程池、无取消机制。
- 工作线程**绝不触碰 Tk**：所有 UI 更新都经 `_enqueue_ui_call()` 投进 `queue.Queue`。
- 主线程用 `_process_ui_queue()` 每 50ms 自调度消费该队列；单个回调抛异常只吞掉自己，
  **泵必须继续续排**——否则下载进度、成功回调、失败弹窗会全部永久静默。
- 任务代际用单调递增的 `_active_task_id` 判定：过期回调一律丢弃。
- 关窗统一走 `_on_close()`：确认在飞任务 → 取消所有挂起的 `after`
  （含 matplotlib 的 `_idle_draw_id`）→ `quit()` → `destroy()`。

## 五、关键契约

改代码时这些是"对外承诺"，不要悄悄破坏：

1. **进度回调** `progress_callback(downloaded_bytes, total_bytes, file_index, file_count)`
   四个位置参数；`downloaded_bytes` 跨文件累计且单调不减；末事件恒为满值；按文件粒度触发。
2. **单位**：IR/WV → 摄氏度；VIS → 反射率百分数。`Scene.unit_kind` 只取
   `brightness_temperature` / `reflectance`。
3. **数组所有权**：`Scene.data` 等一律是 copy 而非视图，调用方可安全持有。
4. **资源关闭**：任何失败路径都必须关闭已打开的 dataset；关闭异常不得掩盖处理异常，
   但处理成功时关闭异常必须暴露。
5. **错误文案**：面向用户的消息不得含 traceback；`No CMIPF scan` / `unrecognized engine`
   等固定文案被 GUI 用于分支映射。
6. **模块导入双形态**：包内 / 直接跑脚本 / PyInstaller 冻结三种形态都要能导入。
   冻结后包名 `himawari_ir_toolkit` 不存在，所以必须"包名优先、顶层名兜底"。
7. **导入期不得抛**：`draw_ir_fulldisk` 在导入时就解析缓存目录，必须永远成功
   （三级回落），否则打包后启动即崩。

## 六、扩展点：新增一颗卫星

需要同步改动的地方（目前是硬编码在多个文件里，容易漏）：

1. `satellite_providers.py` → `PROVIDER_CONFIGS`：regions / minutes / bucket / label / 归档窗口
2. `satellite_providers.py` → `_GOES_CHANNELS`：逻辑波段 → ABI 通道映射（仅 GOES 类）
3. `himawari_gui.py` → `PLATFORM_OPTIONS`：下拉框选项
4. `himawari_gui.py` → `_platform_identifier()`：显示名 → 内部标识的映射
5. 测试：`test_satellite_providers.py` 里有对配置表的精确比对与归档边界断言

> 这四处重复是已知技术债：`PROVIDER_CONFIGS` 已经是单一事实来源，但 GUI 侧仍各存一份。

## 七、已踩过的坑（改代码前先看一眼）

| 坑 | 表现 | 根因 |
|---|---|---|
| 冻结导入 | exe 启动即崩，`No module named 'himawari_ir_toolkit'` | 非包模式仍用包名限定导入；且有测试断言禁止顶层名兜底，把 bug 锁成契约 |
| 导入期建目录 | 只读安装位置启动即崩 | `os.makedirs` 无兜底，且发生在 import 阶段 |
| UI 泵停摆 | 按钮一直灰、状态栏卡住 | `_process_ui_queue` 无异常隔离，一次回调抛错就不再续排 |
| 退出噪音 | `bgerror ... invalid command name` | after 未存 id；matplotlib TkAgg 的 `after_idle` 重绘；只 destroy 不 quit |
| 主题阴阳脸 | 深色下状态栏/错误框是浅色 | 直接引用浅色模块常量而非主题令牌 |
| 字号区域特例 | GOES 与 Himawari 同尺寸字号不一致 | `if region_full == "FLDK"` 特例，而 GOES 传的是 `"F"` |
| 源码字符串断言 | 等价重构就红 | 测试断言实现细节而非行为；建议改成断言契约（如"必须走主题令牌") |

## 八、测试的组织方式

- 全部为 `unittest`（环境内无 pytest）。
- `test_satellite_providers.py`：数据层，纯逻辑 + 手写替身，覆盖最扎实。
- `test_download_progress.py`：引擎层，`MagicMock` 掉 fig/ax 断言 imshow 参数与进度语义。
- `test_gui_threading.py`：GUI 层，用 `_ForbiddenVar` / `_ForbiddenButton` 一旦被工作线程
  触碰即失败；另有真实 Tk 用例（无图形环境自动 skip）。
- `test_target_graticule.py`：几何与布局度量，`Agg` 后端。

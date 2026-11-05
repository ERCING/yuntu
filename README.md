# HimawariIRToolkit · 卫星云图分析工具

从 AWS 公开数据源拉取静止气象卫星全圆盘观测，渲染成带装饰（标题栏、色标柱、海岸线/国界）的高分辨率发布级 PNG。提供 **图形界面** 与 **命令行** 两种用法，共用同一套渲染引擎。

支持 **Himawari-9** 与 **GOES-16 / 17 / 18 / 19**，产品覆盖红外窗区、水汽、可见光三类共 11 种专业色阶。

---

## 目录

- [功能](#功能)
- [环境要求](#环境要求)
- [安装](#安装)
- [图形界面](#图形界面)
- [命令行](#命令行)
- [产品矩阵](#产品矩阵)
- [数据来源与可用时段](#数据来源与可用时段)
- [输出文件](#输出文件)
- [测试](#测试)
- [打包](#打包)
- [常见问题](#常见问题)
- [已知限制](#已知限制)
- [目录结构](#目录结构)

---

## 功能

- 全圆盘 / 目标区域成像，投影由卫星元数据驱动（`ccrs.Geostationary`）
- 装饰模式：顶部信息栏（卫星/产品/时次/极值）、右侧色标柱、50m 海岸线与国界、外边框
- **装饰像素锁定**：装饰尺寸按固定像素预算换算，与 DPI、画布尺寸解耦，避免超大图导出后被查看器缩小导致文字过小
- 可见光超大数据自动降采样（最长边上限 11000px）
- 下载进度回调（字节级、单调递增、跨文件累计）
- 双主题（浅色专业 / 深色）图形界面，响应式分档布局

## 环境要求

| 项 | 版本 |
|---|---|
| Python | 3.13（开发与验证环境为 3.13.5） |
| 操作系统 | Windows（`start_gui.bat` 与打包脚本按 Windows 编写） |
| 网络 | 需可访问 AWS S3 公开数据集（匿名读取，无需凭证） |

依赖见 [`requirements.txt`](requirements.txt)：numpy / pandas / matplotlib / cartopy / Pillow / pycontrails / xarray / s3fs / h5netcdf / h5py / pyinstaller。

## 安装

```bat
cd E:\ai\fldk
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> `start_gui.bat` 固定使用项目根目录下的 `.venv`，路径不一致会直接报错退出。

## 图形界面

```bat
start_gui.bat
```

或直接运行：

```bat
.venv\Scripts\python.exe himawari_ir_toolkit\himawari_gui.py
```

界面为三栏工作台：左侧参数区（日期、时次、平台、区域、数据类型、波段、色阶），中间图像预览（滚轮缩放、拖拽平移），右侧图层栏，底部状态栏。窗口默认 1280×800，最小 1024×680。

绘制流程：点击「绘制云图」→ 后台线程下载并渲染 → 完成后自动载入预览 → 可「另存为」。后台任务期间按钮禁用，状态栏显示下载进度。

## 命令行

```bat
.venv\Scripts\python.exe himawari_ir_toolkit\draw_ir_fulldisk.py [参数]
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--time` | `2025-07-24T06:00:00` | UTC 时间，格式 `YYYY-MM-DDTHH:MM:SS` |
| `--platform` | `Himawari-9` | `Himawari-9` / `GOES-16` / `GOES-17` / `GOES-18` / `GOES-19` |
| `--data-type` | `IR` | `IR` / `WV` / `VIS` |
| `--band` | 按数据类型取默认 | IR：`B13`/`B14`；WV：`B08`/`B09`/`AVG`；VIS：`B03` |
| `--scheme` | 按数据类型取默认 | 见[产品矩阵](#产品矩阵色阶) |
| `--region` | `F` | `F` 全圆盘 / `T` 目标区域（**仅 Himawari-9 支持**） |
| `--dpi` | `150` | 输出 DPI，只改变物理尺寸 |
| `--out` | 自动命名 | 输出路径 |
| `--decorations` | 关闭 | 添加边框、标题栏、时间与色标柱 |
| `--list` | — | 列出全部可用色阶及其温度范围与断点数 |

示例：

```bat
:: 全圆盘红外，带装饰
.venv\Scripts\python.exe himawari_ir_toolkit\draw_ir_fulldisk.py --decorations --time 2026-08-07T09:00:00

:: GOES-18 全圆盘红外 BD 增强
.venv\Scripts\python.exe himawari_ir_toolkit\draw_ir_fulldisk.py ^
    --platform GOES-18 --time 2026-08-01T09:00:00 --band B14 --scheme IR-BD --decorations

:: 列出所有色阶
.venv\Scripts\python.exe himawari_ir_toolkit\draw_ir_fulldisk.py --list
```

## 产品矩阵

### 平台

| 平台 | 区域 | 时次粒度 | 数据源 |
|---|---|---|---|
| Himawari-9 | `F` / `T` | 每小时 | pycontrails（`noaa-himawari9`） |
| GOES-16 | `F` | 每 10 分钟 | `noaa-goes16` `ABI-L2-CMIPF` |
| GOES-17 | `F` | 每 10 分钟 | `noaa-goes17` |
| GOES-18 | `F` | 每 10 分钟 | `noaa-goes18` |
| GOES-19 | `F` | 每 10 分钟 | `noaa-goes19` |

### 波段与色阶

| 数据类型 | 波段（默认加粗） | 色阶（默认加粗） | 单位 |
|---|---|---|---|
| IR 红外窗区 | **B14** / B13 | **IR-CC**、IR-BD、IR-CA、IR-OTT、IR-RAMMB、IR-RBTOP、IR-WK | °C |
| WV 水汽 | **AVG** / B08 / B09 | **WV**、WV-SSD | °C |
| VIS 可见光 | **B03** | **VIS-GRAY**、VIS-ENH | % |

GOES 侧的逻辑波段会映射到 ABI 通道：B13→C13、B14→C14、B08→C08、B09→C09、B03→**C02**（0.64µm）；`WV AVG` 取 C08 与 C09 的**逐像元中值**。

## 数据来源与可用时段

数据来自 AWS Open Data 的匿名 S3 读取，**无需任何凭证**。

GOES 各卫星的可用归档窗口（超出范围会在发起网络请求前直接报错）：

| 平台 | 起始 | 结束 |
|---|---|---|
| GOES-16 | 2017-12-18 | 2025-04-06 |
| GOES-17 | 2018-12-04 | 2023-01-10 |
| GOES-18 | 2023-01-04 | 至今 |
| GOES-19 | 2025-04-07 | 至今 |

> GOES 只提供每 10 分钟一个时次（分钟数必须是 00/10/20/30/40/50，且秒必须为 0）。缺少该时次时会明确报错，**不会静默回退到相邻时次**。
> Himawari 走 pycontrails，首次运行会在 `himawari_ir_toolkit/pycontrails_cache/` 建立本地缓存，之后相同时次可命中缓存。

## 输出文件

未指定 `--out` 时，图片写入**当前工作目录**下的 `data/` 子目录（不存在的目录会自动创建）：

- Himawari：`data/himawari_{data_type}_{band}_{region}_{time}_{scheme}.png`
- GOES：`data/{platform}_{data_type}_{band}_FLDK_{scan_start}_{scheme}.png`

未开启装饰时，输出像素与数据像素严格 1:1；开启装饰后宽度会额外增加约 0.12 英寸的色标柱空间。

## 测试

测试用 **unittest**（不是 pytest）：

```bat
.venv\Scripts\python.exe -m unittest discover -s himawari_ir_toolkit\tests -t . -v
```

> 在 PowerShell 里给该命令加 `2>&1` 会把 unittest 的 stderr 输出判成 `NativeCommandError`，导致退出码不可信。判断成败请看重定向后的 `OK` / `FAILED` 与单独的 `$LASTEXITCODE`。

## 打包

```bat
.venv\Scripts\pyinstaller.exe HimawariIRToolkit.spec
```

产物为**目录模式**（`EXE(exclude_binaries=True)` + `COLLECT`，非单文件）。默认输出到 `dist/HimawariIRToolkit/`，分发时需整体拷贝该目录（含同级 `_internal/`）。

> 仓库里 `build/dist/`、`build/work/` 下的历史产物是指定了 `--distpath build/dist --workpath build/work` 打出来的；用上面的默认命令则会落在 `dist/`。两者都在 `.gitignore` 内。

`.spec` 里对 `pycontrails` 做了全量收集——它在 `draw_ir_fulldisk` 中为函数内惰性导入，静态分析扫不到，漏收会导致打包后 Himawari 功能失效。

> **改动模块间导入语句前请先读这条**：冻结后所有模块都变成**顶层模块**，包名
> `himawari_ir_toolkit` 在包里并不存在。因此 `draw_ir_fulldisk.py` 与
> `satellite_providers.py` 的模块间导入必须是"包名优先、顶层名兜底"的双分支写法
> （见这两处 `if __package__:` 块）。写成单一的包名限定导入，开发与测试全都能过，
> 但打包后的 exe 会直接弹 `Unhandled exception in script` 并报
> `ModuleNotFoundError: No module named 'himawari_ir_toolkit'`。
> 曾有测试断言 `assertNotIn("mycolor", ...)` 把错误写法锁成契约，导致这个问题长期没被发现。

## 常见问题

**`ValueError: unrecognized engine 'h5netcdf' must be one of your download engines`**
缺少 NetCDF 读取后端。执行 `.venv\Scripts\python.exe -m pip install h5netcdf h5py`。

**`ValueError: No CMIPF scan ...`**
该卫星在该 UTC 时次没有可用全圆盘数据。常见原因：时间不在归档窗口内、分钟不是 10 的整数倍、或该时次尚未归档。先用相邻时次试。

**`ValueError: Invalid CMIPF slot`**
GOES 的时次必须是整 10 分钟且秒为 0（例如 `09:20:00` 而不是 `09:20:17`）。

**`ValueError: Invalid region for GOES-xx`**
GOES 只支持全圆盘（`--region F`）。目标区域仅 Himawari-9 支持。

**控制台中文报错显示为乱码**
Windows 控制台默认 GBK。执行 `chcp 65001`，或设置环境变量 `PYTHONUTF8=1` 后再运行。这只影响终端显示，不影响出图与 GUI。

**输出图去哪里了？**
当前工作目录下的 `data/`。用 `--out` 可显式指定。

**下载很慢 / 一直卡在「正在下载」**
先确认代理是否真的被程序用上。本程序会**自动读取 Windows 系统代理**（`Internet 选项` 里的设置）并转成 `HTTP_PROXY`/`HTTPS_PROXY`；但要注意代理客户端里如果给 `amazonaws.com` 配了 DIRECT 规则，流量仍然走直连。

实测参考（同一文件 23MB）：直连 0.23 MB/s、走代理 3.78 MB/s。
自测命令：

```powershell
curl.exe -s -o NUL --max-time 30 -r 0-16777215 -w "%{speed_download}`n" `
  https://noaa-goes18.s3.amazonaws.com/ABI-L2-CMIPF/2026/213/09/OR_ABI-L2-CMIPF-M6C14_G18_s20262130900225_e20262130909533_c202621310016.nc
```

输出为字节/秒，除以 1048576 即 MB/s。低于 1 MB/s 建议在代理客户端里把
`*.amazonaws.com` 与 `*.cloudfront.net` 的规则改成走代理节点。
设 `HIMAWARI_NO_SYSTEM_PROXY=1` 可关闭自动读系统代理的行为。

**首次运行很慢**
首次需从 S3 拉取原始数据（全圆盘单文件约 23MB，WV AVG 需两个文件）。

## 已知限制

- 目标区域（`--region T`）仅 Himawari-9 支持，GOES 一律全圆盘。
- 渲染引擎为阻塞式调用，**没有中途取消机制**：下载/绘制过程中关闭 GUI 会中断任务，可能残留写了一半的 PNG。
- GUI 右侧图层栏（图层开关、色阶下拉、`vmin`/`vmax`、反转、等值线）当前**尚未接线**，操作不会影响出图。
- 经纬网：引擎里已有实现与测试，但**按产品决定不接入渲染路径**，界面上对应勾选框为空转控件。
- 无配置持久化：GUI 每次启动恢复默认参数。
- S3 请求已设连接/读取超时（15s/60s）与 2 次重试；代理客户端规则不当仍会走直连，详见常见问题。

更详细的存量问题与后续计划见 [`docs/PROGRESS.md`](docs/PROGRESS.md)。

## 目录结构

```
himawari_ir_toolkit/
├── himawari_gui.py          Tkinter 图形界面（双主题、响应式、线程调度）
├── draw_ir_fulldisk.py      渲染引擎 + 命令行入口（两条管线：Himawari / GOES）
├── satellite_providers.py   平台配置、S3 发现与下载、Scene 组装
├── satellite_scene.py       冻结 dataclass：Scene / ProjectionMetadata
├── mycolor.py               11 套色阶表 → matplotlib Colormap
├── data/                    本地示例产物
└── tests/                   unittest 测试套件
docs/
├── ARCHITECTURE.md          分层、数据流、关键契约、扩展点与已踩过的坑
├── PROGRESS.md              进度、验证状态与已知问题
├── superpowers/specs/       设计规格
├── superpowers/plans/       实施计划
└── mockups/                 界面布局备选方案
requirements.txt / start_gui.bat / HimawariIRToolkit.spec
```

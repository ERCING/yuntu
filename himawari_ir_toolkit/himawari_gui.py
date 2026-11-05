"""
Himawari-9 / GOES 卫星云图分析工具 GUI
双主题（浅色专业 / 深色）· 三栏工作台：参数区 | 图像区 | 图层栏
支持选择日期时间、数据类型和色阶方案
"""

import sys
import os
import threading
import datetime
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import traceback
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from draw_ir_fulldisk import draw_ir_fulldisk, DATA_TYPES
from satellite_providers import get_archive_window, get_provider_config


PLATFORM_OPTIONS = ('Himawari-9', 'GOES-16', 'GOES-17（历史）', 'GOES-18', 'GOES-19')

# ============================================================
# 浅色专业主题调色板（模块级单一事实来源）
# 所有控件与样式一律引用此处常量，禁止在控件构造处重复写裸色值字符串，
# 否则会像此前一样出现「样式表 / 控件 / 状态色」三份互相漂移的色值。
# ============================================================
BG_WINDOW = '#f7f8fa'       # 窗口背景
BG_PANEL = '#ffffff'        # 面板/卡片背景
BG_INPUT = '#f9fafb'        # 输入框背景
BG_HOVER = '#f3f4f6'        # 悬停背景
BG_SURFACE = '#f9fafb'      # 次级表面

BORDER = '#e5e7eb'          # 边框色
BORDER_STRONG = '#d1d5db'   # 强调边框
BORDER_FOCUS = '#2563eb'    # 聚焦边框

TEXT_PRIMARY = '#1f2937'    # 主要文字
TEXT_SECONDARY = '#374151'  # 次要文字
TEXT_MUTED = '#6b7280'      # 弱化文字
TEXT_SUBTLE = '#9ca3af'     # 最弱化文字

PRIMARY = '#2563eb'         # 主色调（专业蓝）
PRIMARY_HOVER = '#1d4ed8'   # 主色悬停
PRIMARY_PRESSED = '#1e40af' # 主色按下
PRIMARY_LIGHT = '#eff6ff'   # 主色浅背景
PRIMARY_BORDER = '#bfdbfe'  # 主色边框
PRIMARY_FG = '#ffffff'      # 主色前景

SUCCESS = '#059669'         # 成功色
SUCCESS_BG = '#ecfdf5'      # 成功背景
SUCCESS_BORDER = '#a7f3d0'  # 成功边框
WARNING = '#d97706'         # 警告色
ERROR = '#dc2626'           # 错误色
ERROR_BG = '#fef2f2'        # 错误背景
ERROR_BORDER = '#fecaca'    # 错误边框
ERROR_BORDER_ACTIVE = '#fca5a5'  # 危险按钮悬停边框
BORDER_HOVER = '#9ca3af'    # 次按钮悬停边框

# 图像画布外围底色（浅色主题）与云图自身底色（导出图是黑底，保持不变）
STAGE_BG = '#eef1f5'
FIGURE_BG = '#070a0e'

# ============================================================
# 深色主题调色板（与 .design/colors_and_type.css 的 html.dark 逐值对应）
# ============================================================
THEME_FONTS = ('Segoe UI', 'Microsoft YaHei UI')

DARK_BG_WINDOW = '#0f1319'
DARK_BG_PANEL = '#161b23'
DARK_BG_POPOVER = '#1b2129'
DARK_BG_INPUT = '#12171e'
DARK_BG_HOVER = '#1e242d'
DARK_BG_SURFACE = '#1b2129'

DARK_BORDER = '#262d38'
DARK_BORDER_STRONG = '#333b48'
DARK_BORDER_FOCUS = '#3b82f6'

DARK_TEXT_PRIMARY = '#e5e7eb'
DARK_TEXT_SECONDARY = '#cbd5e1'
DARK_TEXT_MUTED = '#9ca3af'
DARK_TEXT_SUBTLE = '#6b7280'

DARK_PRIMARY = '#3b82f6'
DARK_PRIMARY_HOVER = '#2563eb'
DARK_PRIMARY_PRESSED = '#1d4ed8'
DARK_PRIMARY_LIGHT = '#16243a'
DARK_PRIMARY_BORDER = '#1e3a5f'
DARK_PRIMARY_FG = '#ffffff'

DARK_SUCCESS = '#34d399'
DARK_SUCCESS_BG = '#0f2a22'
DARK_SUCCESS_BORDER = '#1d4b3d'
DARK_WARNING = '#fbbf24'
DARK_ERROR = '#f87171'
DARK_ERROR_BG = '#2b1518'
DARK_ERROR_BORDER = '#4c2226'

DARK_STAGE_BG = '#0b0f14'


def light_palette():
    """浅色主题令牌表。所有键在两个主题里必须完全一致，否则切换会 KeyError。"""
    return {
        'window': BG_WINDOW, 'panel': BG_PANEL, 'surface': BG_SURFACE,
        'input': BG_INPUT, 'hover': BG_HOVER, 'popover': BG_PANEL,
        'border': BORDER, 'border_strong': BORDER_STRONG, 'border_hover': BORDER_HOVER,
        'border_focus': BORDER_FOCUS,
        'text': TEXT_PRIMARY, 'text_secondary': TEXT_SECONDARY,
        'text_muted': TEXT_MUTED, 'text_subtle': TEXT_SUBTLE,
        'primary': PRIMARY, 'primary_hover': PRIMARY_HOVER,
        'primary_pressed': PRIMARY_PRESSED, 'primary_light': PRIMARY_LIGHT,
        'primary_border': PRIMARY_BORDER, 'primary_fg': PRIMARY_FG,
        'success': SUCCESS, 'success_bg': SUCCESS_BG, 'success_border': SUCCESS_BORDER,
        'warning': WARNING, 'error': ERROR, 'error_bg': ERROR_BG,
        'error_border': ERROR_BORDER, 'error_border_active': ERROR_BORDER_ACTIVE,
        'stage': STAGE_BG,
    }


def dark_palette():
    """深色主题令牌表。"""
    return {
        'window': DARK_BG_WINDOW, 'panel': DARK_BG_PANEL, 'surface': DARK_BG_SURFACE,
        'input': DARK_BG_INPUT, 'hover': DARK_BG_HOVER, 'popover': DARK_BG_POPOVER,
        'border': DARK_BORDER, 'border_strong': DARK_BORDER_STRONG,
        'border_hover': DARK_TEXT_MUTED,
        'border_focus': DARK_BORDER_FOCUS,
        'text': DARK_TEXT_PRIMARY, 'text_secondary': DARK_TEXT_SECONDARY,
        'text_muted': DARK_TEXT_MUTED, 'text_subtle': DARK_TEXT_SUBTLE,
        'primary': DARK_PRIMARY, 'primary_hover': DARK_PRIMARY_HOVER,
        'primary_pressed': DARK_PRIMARY_PRESSED, 'primary_light': DARK_PRIMARY_LIGHT,
        'primary_border': DARK_PRIMARY_BORDER, 'primary_fg': DARK_PRIMARY_FG,
        'success': DARK_SUCCESS, 'success_bg': DARK_SUCCESS_BG,
        'success_border': DARK_SUCCESS_BORDER,
        'warning': DARK_WARNING, 'error': DARK_ERROR, 'error_bg': DARK_ERROR_BG,
        'error_border': DARK_ERROR_BORDER, 'error_border_active': DARK_ERROR,
        'stage': DARK_STAGE_BG,
    }


THEMES = {'light': light_palette, 'dark': dark_palette}


def _blend_hex(color_a, color_b, ratio):
    """在两个 #rrggbb 之间线性插值，ratio=0 返回 color_a。"""
    ratio = max(0.0, min(1.0, ratio))
    channels = []
    for offset in (1, 3, 5):
        start = int(color_a[offset:offset + 2], 16)
        end = int(color_b[offset:offset + 2], 16)
        channels.append(int(round(start + (end - start) * ratio)))
    return '#{:02x}{:02x}{:02x}'.format(*channels)


def _platform_identifier(display):
    return 'GOES-17' if display == 'GOES-17（历史）' else display


# ============================================================
# 响应式尺度令牌
# ============================================================
# Tk 的 font size 是「点」，不是像素；Windows 上 1pt ≈ 1.33px @96dpi。
# HTML 稿基准是 11-15px，本工程早期用的是 8-10pt（≈11-13px）但被系统
# 125% 缩放二次压缩后视觉上只有 ~8px，这就是「字体太小」的来源。
# 这里按窗口宽度分四档整体放大，并把字号统一收口到 _font()，禁止散落硬编码。
FONT_FAMILY = ('Segoe UI', 'Microsoft YaHei UI')

# 档位：(窗口宽度下限, 主字号, 次级字号, 微字号)
# 注意：primary 用 DPI 校正后的自适应值，见 HimawariGUI._measure_scale()
SCALE_TIERS = (
    (1600, 12.0, 10.5, 9.5),
    (1400, 11.0, 10.0, 9.0),
    (1200, 10.5, 9.5, 9.0),
    (0,    10.0, 9.0,  8.5),
)

# 栏宽档位：(窗口宽度下限, 左参数区, 右图层栏, 是否常显状态栏次要信息)
RAIL_TIERS = (
    (1600, 320, 288, True),
    (1400, 304, 272, True),
    (1200, 288, 256, False),
    (0,    268, 236, False),
)


def _tier_for(width, tiers):
    """按窗口宽度取档位；tiers 需按宽度降序排列。"""
    for tier in tiers:
        if width >= tier[0]:
            return tier
    return tiers[-1]


class HimawariGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Satellite IR Toolkit · 卫星云图分析")
        self.root.geometry("1280x800")
        self.root.minsize(1024, 680)
        
        # 当前图片数据
        self.current_image_path = None
        self.current_data = None
        self.current_extent = None
        
        # matplotlib 相关
        self.fig = None
        self.ax = None
        self.canvas = None
        
        # 缩放和平移相关
        self.original_img = None
        self.current_resized_img = None
        self.current_tk_image = None
        self.zoom_scale = 1.0
        self.image_offset_x = 0
        self.image_offset_y = 0
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.image_item_id = None
        self.zoom_after_id = None
        self.ui_queue = queue.Queue()
        self._next_task_id = 0
        self._active_task_id = None

        # 主题系统
        self._theme = 'light'
        # tk 控件登记表：[(widget, {'bg': 'panel', 'fg': 'text'}), ...]
        # tk.Label / tk.Frame 不吃 ttk.Style，切换主题必须逐控件重配，
        # 因此构造期统一登记，_apply_theme 时统一回放，避免漏改出「阴阳脸」。
        self._theme_widgets = []
        # 画布类控件登记表：[(canvas, {'bg': 'stage', 'line': 'border'}), ...]
        self._theme_canvases = []
        # 字体登记表：[(widget, role, bold), ...]
        # ttk 样式能重建，但 tk.Label/Checkbutton/Entry 的 font 必须逐个重设，
        # 否则缩窗跨档位时字号不变 → 大字挤压小空间，直接导致重叠。
        self._font_widgets = []

        # 响应式状态
        # Tk 会按系统 DPI 缩放「点」→像素，这里读取实测缩放比，
        # 让 fontsize 在高 DPI 屏上不至于被二次放大/压缩。
        self._ui_scale = self._measure_scale()
        self._layout_width = 0       # 上一次生效的窗口宽度（档位判定基准）
        self._layout_tier = None     # 上一次生效的栏宽档位，用于跳过无变化的样式重建
        self._resize_after_id = None
        self._compact = False        # 窄窗模式：隐藏状态栏次要信息

        # 生命周期状态：关窗流程与在飞任务
        self._closing = False        # 关窗已启动：UI 泵停止续排
        self._draw_in_flight = False  # 后台绘制线程是否仍在运行
        self._pump_after_id = None   # UI 泵的 after id，关窗时必须取消
        self._initial_layout_after_id = None  # 首帧布局回填的 after id

        # 初始化UI
        self._setup_styles()
        self._init_ui()
        self._bind_responsive()
        self._process_ui_queue()
        # 关窗统一走 _on_close，而不是让 Tk 直接销毁窗口
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    # ============================================================
    # 响应式尺度
    # ============================================================
    def _measure_scale(self):
        """读取系统 DPI 缩放比（1.0 / 1.25 / 1.5 ...），并夹在合理区间。"""
        try:
            scale = float(self.root.winfo_fpixels('1i')) / 96.0
        except (tk.TclError, ValueError):
            scale = 1.0
        return min(max(scale, 1.0), 3.0)

    def _font(self, role='body', bold=False):
        """统一字号入口。

        role:
          - display  品牌标题（顶栏主标题）
          - heading  卡片 / 分区标题
          - body     正文、标签、下拉框、按钮
          - caption  辅助说明
          - micro    极小号（色带刻度、状态栏数据源）
        返回 Tk 可接受的 (family, size, *styles) 元组。
        """
        width = self._layout_width or self.root.winfo_width()
        if width <= 1:
            width = 1280
        _, primary, secondary, micro = _tier_for(width, SCALE_TIERS)
        # 高 DPI 下 pt→px 已被放大，再乘系数会过大；低 DPI 下需要补一点
        dpi_fix = 1.0 if self._ui_scale <= 1.05 else 1.0 / min(self._ui_scale, 1.5)

        if role == 'display':
            size = primary + 3.0
        elif role == 'heading':
            size = primary + 1.0
        elif role == 'caption':
            size = secondary
        elif role == 'micro':
            size = micro
        else:
            size = primary

        # 真实 Tk 只接受整数字号（传 13.5 会抛 expected integer），必须取整；
        # 四舍五入到 0.5 再 int，保证档位间的差异不小于 1pt，避免「看起来一样大」。
        size = int(round(max(9.0, round(size * dpi_fix * 2) / 2.0)))
        # Tk 的 size 为负数时表示像素，这里统一用点（正数），便于 DPI 自适应
        family = FONT_FAMILY[0]
        return (family, size, 'bold') if bold else (family, size)

    def _bind_responsive(self):
        """绑定根窗口尺寸变化，按宽度分档重排布局。

        为什么必须绑：minsize 是 1024×680，减去左右两栏后中栏只剩 ~460px，
        如果不做分档，字大一档就会立刻压盖。这里在 <Configure> 上做
        防抖（80ms），因为一次拖拽会连续触发几十次事件，
        每次都重建 ttk 样式 + 重配全部字体，主线程会被打满。
        """
        self.root.bind('<Configure>', self._on_root_configure, add='+')
        # 首帧还没拿到真实宽度，等窗口映射完成后再做一次布局。
        # 必须存下 id：窗口若在这之前就被关闭，这条 pending 的 after 会在
        # 销毁之后触发，报 bgerror "invalid command name ..._refresh_responsive"。
        self._initial_layout_after_id = self.root.after(0, self._refresh_responsive)

    def _on_root_configure(self, event=None):
        """<Configure> 防抖：只在根窗口宽度真正跨档或变化时才重排。"""
        if event is not None and event.widget is not self.root:
            return
        width = self.root.winfo_width()
        if width <= 1:
            return
        if width == self._layout_width:
            return
        if self._resize_after_id is not None:
            try:
                self.root.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
        self._resize_after_id = self.root.after(80, self._refresh_responsive)

    def _refresh_responsive(self):
        """按当前窗口宽度重算档位：栏宽、字号、次要元素显隐。"""
        self._resize_after_id = None
        self._initial_layout_after_id = None
        width = self.root.winfo_width()
        if width <= 1:
            return
        if width == self._layout_width:
            return
        self._layout_width = width

        _, left_width, right_width, compact = _tier_for(width, RAIL_TIERS)
        self._compact = not compact

        # 栏宽：pack_propagate(False) 的固定宽栏必须显式改 width，
        # 否则缩窗时它仍占旧宽度，把中栏挤成负空间 → 控件重叠。
        sidebar = getattr(self, '_sidebar', None)
        if sidebar is not None:
            try:
                sidebar.configure(width=left_width)
            except tk.TclError:
                pass
        rail = getattr(self, '_rail', None)
        if rail is not None:
            try:
                rail.configure(width=right_width)
            except tk.TclError:
                pass

        # 画布内边距：窄窗收紧，给云图本体留像素
        pad = 16 if width >= 1200 else (10 if width >= 1024 else 6)
        canvas_widget = getattr(self, '_canvas_widget', None)
        if canvas_widget is not None:
            try:
                canvas_widget.pack_configure(padx=pad, pady=pad)
            except tk.TclError:
                pass

        # 次要元素显隐：窄窗直接隐藏，而不是让它去挤压主信息。
        # 恢复时必须还原原 pack 参数（side/边距），否则控件会跳到错误位置或丢掉间距。
        for entry in getattr(self, '_responsive_extras', ()):
            widget, kwargs = entry if isinstance(entry, tuple) else (entry, {'side': tk.RIGHT})
            try:
                if compact:
                    widget.pack_forget()
                else:
                    widget.pack(**kwargs)
            except tk.TclError:
                pass

        # ttk 样式（含 font）重建 + tk.* 控件字体逐个重设
        self._setup_styles()
        font_pal = self._font_family_objects()
        for widget, role, bold in self._font_widgets:
            try:
                widget.configure(font=font_pal(role, bold))
            except tk.TclError:
                pass
        # 时间轴是单画布，整条重绘一次即可（不是 12 次）
        self._paint_timeline()
        self._paint_ramp_preview()

    def _font_family_objects(self):
        """把 _font 包成可复用的闭包，避免在循环里反复做档位计算。"""
        cache = {}

        def _get(role, bold):
            key = (role, bold)
            if key not in cache:
                cache[key] = self._font(role, bold)
            return cache[key]

        return _get

    # ============================================================
    # 主题
    # ============================================================
    def _pal(self, token):
        """取当前主题下某个令牌的色值。

        对没有 _theme 属性的实例（测试常用 object.__new__ 造壳）按浅色兜底，
        避免新增调用点因为没走完整构造就直接 AttributeError。
        """
        theme = getattr(self, '_theme', 'light')
        return THEMES[theme if theme in THEMES else 'light']()[token]

    def _register(self, widget, **tokens):
        """登记 tk 控件：tokens 形如 bg='panel', fg='text'。"""
        self._theme_widgets.append((widget, tokens))
        return widget

    def _register_canvas(self, canvas, **tokens):
        self._theme_canvases.append((canvas, tokens))
        return canvas

    def _toggle_theme(self):
        self._apply_theme('dark' if self._theme == 'light' else 'light')

    def _apply_theme(self, theme):
        """切换主题：重配 ttk 样式 → 回放 tk 控件色值 → 重绘画布图形。"""
        self._theme = theme if theme in THEMES else 'light'
        self._setup_styles()
        pal = THEMES[self._theme]()
        for widget, tokens in self._theme_widgets:
            try:
                widget.configure(**{key: pal[token] for key, token in tokens.items()})
            except tk.TclError:
                pass
        for canvas, tokens in self._theme_canvases:
            self._paint_canvas(canvas, tokens)
        # 时间轴刻度与色带预览都是 canvas 图形项，需整体重建
        for tick, hour in getattr(self, 'timeline_ticks', ()):
            self._paint_tick(tick, hour)
        self._paint_ramp_preview()
        self._apply_stage_theme()
        self._update_theme_button()
        # 状态栏前景色由「最后一次状态种类」决定，切主题后必须按新令牌重刷，
        # 否则深色主题下还会留着浅色的成功绿 / 错误红
        label = getattr(self, 'progress_label', None)
        if label is not None:
            try:
                label.configure(fg=self._get_status_color(getattr(self, '_status_kind', 'Ready')))
            except tk.TclError:
                pass

    def _apply_stage_theme(self):
        """图像区外围底色跟随主题；云图 figure 本身始终黑底，不改。"""
        container = getattr(self, 'stage_container', None)
        if container is not None:
            try:
                container.configure(bg=self._pal('stage'))
            except tk.TclError:
                pass
        if getattr(self, 'fig', None) is not None:
            self.fig.patch.set_facecolor(FIGURE_BG)

    def _paint_canvas(self, canvas, tokens):
        """canvas 的图形项不随 configure 变色，必须删除重建。"""
        canvas.configure(bg=THEMES[self._theme]()[tokens['bg']])
        if 'line' in tokens:
            canvas.delete('themed')
            width, height = 12, 12
            canvas.create_oval(1, 1, width - 1, height - 1,
                               fill=THEMES[self._theme]()[tokens['line']],
                               outline='', tags='themed')

    def _update_theme_button(self):
        button = getattr(self, 'theme_btn', None)
        if button is None:
            return
        # 目标态而非当前态：按钮文字表示「点下去会变成什么」
        button.configure(text="浅色" if self._theme == 'dark' else "深色")


    def _setup_styles(self):
        """配置当前主题的 ttk 样式（浅色 / 深色共用一套样式名，色值走令牌）"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        p = THEMES[self._theme]()

        # 水平内边距随字号档位缩放，避免大字挤在小 padding 里显得局促
        pad_x = 8 if self._layout_width >= 1200 or self._layout_width <= 1 else 6

        # 根窗口背景
        self.root.configure(bg=p['window'])

        # Frame 样式
        style.configure('Dark.TFrame', background=p['window'])
        style.configure('Panel.TFrame', background=p['panel'])
        style.configure('Card.TFrame', background=p['surface'])
        style.configure('Stage.TFrame', background=p['stage'])

        # 标题栏
        style.configure('TitleBar.TFrame', background=p['panel'])
        style.configure('Title.TLabel',
                        background=p['panel'],
                        foreground=p['text'],
                        font=self._font('display', bold=True))
        style.configure('Subtitle.TLabel',
                        background=p['panel'],
                        foreground=p['text_muted'],
                        font=self._font('caption'))
        style.configure('Version.TLabel',
                        background=p['hover'],
                        foreground=p['text_subtle'],
                        font=self._font('micro'),
                        padding=(pad_x, 3))

        # 侧边栏分区标题
        style.configure('Section.TLabel',
                        background=p['panel'],
                        foreground=p['text_muted'],
                        font=self._font('heading', bold=True))
        style.configure('SectionDivider.TSeparator',
                        background=p['border'])

        # 表单标签
        style.configure('Field.TLabel',
                        background=p['panel'],
                        foreground=p['text_secondary'],
                        font=self._font('body'))

        # 下拉框样式
        style.configure('Dark.TCombobox',
                        fieldbackground=p['input'],
                        background=p['input'],
                        foreground=p['text'],
                        selectbackground=p['primary'],
                        selectforeground=p['primary_fg'],
                        bordercolor=p['border_strong'],
                        lightcolor=p['border_strong'],
                        darkcolor=p['border_strong'],
                        arrowcolor=p['text_muted'],
                        padding=(pad_x, 5),
                        font=self._font('body'))
        style.map('Dark.TCombobox',
                  fieldbackground=[('readonly', p['input']), ('focus', p['panel'])],
                  background=[('active', p['hover']), ('!active', p['input'])],
                  foreground=[('readonly', p['text'])],
                  selectbackground=[('readonly', p['primary'])],
                  selectforeground=[('readonly', p['primary_fg'])],
                  bordercolor=[('focus', p['border_focus']), ('!focus', p['border_strong'])],
                  arrowcolor=[('active', p['text']), ('!active', p['text_muted'])])

        # 下拉列表（ttk 在 Windows 上用的是 Tk listbox，需要单独配色）
        self.root.option_add('*TCombobox*Listbox.background', p['panel'])
        self.root.option_add('*TCombobox*Listbox.foreground', p['text'])
        self.root.option_add('*TCombobox*Listbox.selectBackground', p['primary'])
        self.root.option_add('*TCombobox*Listbox.selectForeground', p['primary_fg'])

        # 按钮样式 - 主按钮
        style.configure('Primary.TButton',
                        background=p['primary'],
                        foreground=p['primary_fg'],
                        borderwidth=0,
                        focusthickness=0,
                        focuscolor='none',
                        font=self._font('body', bold=True),
                        padding=(16, 10),
                        relief='flat')
        style.map('Primary.TButton',
                  background=[('active', p['primary_pressed']),
                              ('!active', p['primary']),
                              ('disabled', p['hover'])],
                  # 禁用态前景统一为当前主题的弱化灰，走令牌而非浅色常量
                  foreground=[('disabled', p['text_subtle']),
                              ('!disabled', p['primary_fg'])],
                  relief=[('pressed', 'flat'), ('!pressed', 'flat')])

        # 按钮样式 - 次按钮
        style.configure('Secondary.TButton',
                        background=p['panel'],
                        foreground=p['text_secondary'],
                        bordercolor=p['border_strong'],
                        borderwidth=1,
                        focusthickness=0,
                        focuscolor='none',
                        font=self._font('body'),
                        padding=(14, 9),
                        relief='solid')
        style.map('Secondary.TButton',
                  background=[('active', p['input']),
                              ('!active', p['panel']),
                              ('disabled', p['hover'])],
                  foreground=[('disabled', p['text_subtle']),
                              ('!disabled', p['text_secondary'])],
                  bordercolor=[('focus', p['primary']),
                               ('active', p['border_hover']),
                               ('!active', p['border_strong'])])

        # 按钮样式 - 危险按钮
        style.configure('Danger.TButton',
                        background=p['panel'],
                        foreground=p['error'],
                        bordercolor=p['error_border'],
                        borderwidth=1,
                        focusthickness=0,
                        focuscolor='none',
                        font=self._font('body'),
                        padding=(14, 9),
                        relief='solid')
        style.map('Danger.TButton',
                  background=[('active', p['error_bg']),
                              ('!active', p['panel']),
                              ('disabled', p['hover'])],
                  foreground=[('disabled', p['text_subtle']),
                              ('!disabled', p['error'])],
                  bordercolor=[('active', p['error_border_active']),
                               ('!active', p['error_border'])])

        # 进度条
        style.configure('Dark.Horizontal.TProgressbar',
                        troughcolor=p['border'],
                        background=p['primary'],
                        bordercolor=p['border'],
                        lightcolor=p['primary'],
                        darkcolor=p['primary'],
                        troughrelief='flat',
                        relief='flat',
                        thickness=6)

        # 状态标签
        style.configure('Status.TLabel',
                        background=p['surface'],
                        foreground=p['text_muted'],
                        font=self._font('body'))
        style.configure('Status.Working.TLabel',
                        background=p['surface'],
                        foreground=p['primary'],
                        font=self._font('body'))
        style.configure('Status.Success.TLabel',
                        background=p['surface'],
                        foreground=p['success'],
                        font=self._font('body'))
        style.configure('Status.Error.TLabel',
                        background=p['surface'],
                        foreground=p['error'],
                        font=self._font('body'))
        style.configure('Status.Ready.TLabel',
                        background=p['surface'],
                        foreground=p['text_muted'],
                        font=self._font('body'))

        # Labelframe 卡片样式
        style.configure('Card.TLabelframe',
                        background=p['panel'],
                        bordercolor=p['border'],
                        borderwidth=1,
                        relief='solid')
        style.configure('Card.TLabelframe.Label',
                        background=p['panel'],
                        foreground=p['text'],
                        font=self._font('heading', bold=True))

        # 状态栏
        style.configure('StatusBar.TFrame', background=p['panel'])
        style.configure('StatusBar.TLabel',
                        background=p['panel'],
                        foreground=p['text_subtle'],
                        font=self._font('caption'))

        # 进度容器
        style.configure('ProgressCard.TFrame',
                        background=p['surface'],
                        bordercolor=p['border'],
                        relief='solid')

        # 工具按钮（小图标按钮）。Tk 无 transparent 概念，用面板色兜底。
        style.configure('Tool.TButton',
                        background=p['panel'],
                        foreground=p['text_muted'],
                        borderwidth=0,
                        focusthickness=0,
                        focuscolor='none',
                        font=self._font('caption'),
                        padding=(8, 5),
                        relief='flat')
        style.map('Tool.TButton',
                  background=[('active', p['hover']), ('!active', p['panel'])],
                  foreground=[('active', p['text']), ('!active', p['text_muted'])])

        # 分段选择器（zoom-fit / zoom-actual 之类）
        style.configure('Segment.TButton',
                        background=p['panel'],
                        foreground=p['text_muted'],
                        borderwidth=1,
                        bordercolor=p['border'],
                        focusthickness=0,
                        focuscolor='none',
                        font=self._font('caption'),
                        padding=(10, 4),
                        relief='solid')
        style.map('Segment.TButton',
                  background=[('active', p['hover']), ('!active', p['panel'])],
                  foreground=[('active', p['text']), ('!active', p['text_muted'])],
                  bordercolor=[('active', p['border_strong']), ('!active', p['border'])])

        # 垂直滚动条
        style.configure('Vertical.TScrollbar',
                        background=p['hover'],
                        troughcolor=p['panel'],
                        bordercolor=p['panel'],
                        arrowcolor=p['text_muted'],
                        lightcolor=p['hover'],
                        darkcolor=p['hover'],
                        relief='flat',
                        arrowsize=12)

    def _init_ui(self):
        """初始化 UI - 标题栏 + 三栏工作台（参数区 | 图像区 | 图层栏）+ 状态栏"""
        # 主容器
        main_frame = ttk.Frame(self.root, style='Dark.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === 顶部标题栏 ===
        self._create_title_bar(main_frame)
        
        # === 底部状态栏 ===
        # 必须在 content_frame 之前 pack：content_frame 带 expand=True，会吃掉
        # main_frame 的全部剩余高度；后 pack 的 status_bar 只剩 0 高、winfo_ismapped()
        # 为 0，整条状态栏被裁掉（截图里底部只剩一条刻度残影就是这个原因）。
        self._create_status_bar(main_frame)

        # === 主内容区（三栏布局）===
        content_frame = ttk.Frame(main_frame, style='Dark.TFrame')
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左：参数区  中：图像区  右：图层栏
        # 注意 pack 顺序 ≠ 视觉顺序：pack(side=LEFT/RIGHT) 按调用先后从两侧
        # 依次「吃」空间，最先 pack 的最贴近窗口边缘。所以左右两栏必须先于
        # 中栏 pack，中栏用 expand 吃掉剩余宽度；反过来先 pack 中栏，它会
        # 抢走全部空间，把后 pack 的两栏挤到 0 宽（早期版本的栏宽错乱根因）。
        self._create_sidebar(content_frame)
        self._create_layer_rail(content_frame)
        self._create_image_view(content_frame)

    # ---------- 通用小构件 ----------
    def _hairline(self, parent, side, horizontal_fill=True):
        """1px 分隔线。Tk 没有 border 属性，用 1px Frame 模拟。"""
        if side in (tk.TOP, tk.BOTTOM):
            line = tk.Frame(parent, bg=self._pal('border'), height=1)
            self._register(line, bg='border')
            line.pack(side=side, fill=tk.X)
        else:
            line = tk.Frame(parent, bg=self._pal('border'), width=1)
            self._register(line, bg='border')
            line.pack(side=side, fill=tk.Y)
        return line

    def _field_label(self, parent, text, margin_top=12):
        label = tk.Label(parent, text=text,
                         bg=self._pal('panel'), fg=self._pal('text_muted'),
                         font=self._font('body'))
        self._register(label, bg='panel', fg='text_muted')
        self._font_widgets.append((label, 'body', False))
        label.pack(anchor=tk.W, pady=(margin_top, 6))
        return label

    def _create_title_bar(self, parent):
        """创建顶部标题栏。

        早期版本用 height=48 + pack_propagate(False) 锁死高度，左右两组控件
        各带 padx=16 且中间没有弹性分隔，窗口一窄就互相压盖。这里改为
        「内容决定高度 + 中间 expand spacer」：任何时候两者都不会重叠，
        放不下时由 pack 自动压缩 spacer 而不是让控件叠在一起。
        """
        title_bar = tk.Frame(parent, bg=self._pal('panel'))
        self._register(title_bar, bg='panel')
        title_bar.pack(fill=tk.X, side=tk.TOP)
        self._hairline(title_bar, tk.BOTTOM)

        # 用一个 content 行承载，竖直 padding 交给它，高度自然跟随字号
        row = tk.Frame(title_bar, bg=self._pal('panel'))
        self._register(row, bg='panel')
        row.pack(fill=tk.X, padx=16, pady=10)

        # 左侧标题
        left_frame = tk.Frame(row, bg=self._pal('panel'))
        self._register(left_frame, bg='panel')
        left_frame.pack(side=tk.LEFT)

        # 品牌标记：Tk 无 SVG，用 Canvas 画一个空心圆 + 圆点，
        # 避免再用 ◎ / ● 这类字符冒充图标（不同字体下渲染不可控）。
        brand = tk.Canvas(left_frame, width=32, height=32, highlightthickness=0,
                          bg=self._pal('primary'))
        self._register(brand, bg='primary')
        brand.create_oval(6, 6, 26, 26, outline=self._pal('primary_fg'), width=2,
                          tags='themed')
        brand.create_oval(13, 13, 19, 19, fill=self._pal('primary_fg'), outline='',
                          tags='themed')
        self._register_canvas(brand, bg='primary')
        brand.pack(side=tk.LEFT, padx=(0, 12))

        title_text_frame = tk.Frame(left_frame, bg=self._pal('panel'))
        self._register(title_text_frame, bg='panel')
        title_text_frame.pack(side=tk.LEFT)

        title_label = tk.Label(title_text_frame, text="Satellite IR Toolkit",
                               bg=self._pal('panel'), fg=self._pal('text'),
                               font=self._font('display', bold=True))
        self._register(title_label, bg='panel', fg='text')
        self._font_widgets.append((title_label, 'display', True))
        title_label.pack(anchor=tk.W)

        self.subtitle_label = tk.Label(title_text_frame,
                                       text="Himawari · GOES 云图分析",
                                       bg=self._pal('panel'), fg=self._pal('text_muted'),
                                       font=self._font('caption'))
        self._register(self.subtitle_label, bg='panel', fg='text_muted')
        self._font_widgets.append((self.subtitle_label, 'caption', False))
        self.subtitle_label.pack(anchor=tk.W)

        # 右侧操作区：数据就绪徽标 + 主题切换 + 版本号
        # 放在 row 里最先 pack 的 RIGHT 组，天然贴右，不会与左侧争位。
        right_frame = tk.Frame(row, bg=self._pal('panel'))
        self._register(right_frame, bg='panel')
        right_frame.pack(side=tk.RIGHT)

        version_label = tk.Label(right_frame, text="v1.3.0",
                                 bg=self._pal('hover'), fg=self._pal('text_subtle'),
                                 font=self._font('micro'),
                                 padx=8, pady=4)
        self._register(version_label, bg='hover', fg='text_subtle')
        self._font_widgets.append((version_label, 'micro', False))
        version_label.pack(side=tk.RIGHT)
        # 窄窗时版本号是最次要的信息，直接隐藏
        self._responsive_extras = [(version_label, {'side': tk.RIGHT})]

        self.theme_btn = ttk.Button(right_frame, text="深色",
                                    command=self._toggle_theme,
                                    style='Segment.TButton')
        self.theme_btn.pack(side=tk.RIGHT, padx=(0, 12))

        status_frame = tk.Frame(right_frame, bg=self._pal('success_bg'))
        self._register(status_frame, bg='success_bg')
        status_frame.pack(side=tk.RIGHT, padx=(0, 12))

        self.title_dot = tk.Canvas(status_frame, width=12, height=12,
                                   highlightthickness=0, bg=self._pal('success_bg'))
        self._register_canvas(self.title_dot, bg='success_bg', line='success')
        self._paint_canvas(self.title_dot, {'bg': 'success_bg', 'line': 'success'})
        self.title_dot.pack(side=tk.LEFT, padx=(8, 5), pady=5)

        status_text = tk.Label(status_frame, text="数据就绪",
                               bg=self._pal('success_bg'), fg=self._pal('success'),
                               font=self._font('caption'))
        self._register(status_text, bg='success_bg', fg='success')
        self._font_widgets.append((status_text, 'caption', False))
        status_text.pack(side=tk.LEFT, padx=(0, 10), pady=5)
        # 标题文字与右侧操作组之间的弹性垫：空间不足时先吃掉它
        self._title_spacer = tk.Frame(row, bg=self._pal('panel'))
        self._register(self._title_spacer, bg='panel')
        self._title_spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # 重排顺序：spacer 必须在 left_frame / right_frame 之间，
        # pack 顺序即占位顺序，所以把 spacer 重新 pack 到 left 之后。
        self._title_spacer.pack_forget()
        self._title_spacer.pack(side=tk.LEFT, fill=tk.X, expand=True, before=right_frame)

    def _create_sidebar(self, parent):
        """创建左侧参数区（宽度由响应式档位控制，可滚动）"""
        _, left_width, _, _ = _tier_for(self._layout_width or 1280, RAIL_TIERS)
        sidebar = tk.Frame(parent, bg=self._pal('panel'), width=left_width)
        self._register(sidebar, bg='panel')
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        # 固定宽度是这个栏的本意（中栏要吃掉剩余空间），但宽度值必须是
        # 档位算出来的，而不是写死 300，否则缩窗时中栏被挤到重叠。
        sidebar.pack_propagate(False)
        self._sidebar = sidebar

        # 右侧分隔线
        self._hairline(sidebar, tk.RIGHT)

        # 可滚动内容区
        canvas = tk.Canvas(sidebar, bg=self._pal('panel'), highlightthickness=0,
                           width=left_width - 1)
        self._register(canvas, bg='panel')
        scrollbar = ttk.Scrollbar(sidebar, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self._pal('panel'))
        self._register(scrollable_frame, bg='panel')

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # 关键：内层窗口宽度必须跟随画布宽度，否则侧栏变窄时内容被裁掉、
        # 变宽时右侧留白。早期漏了这条绑定，是「缩窗后内容溢出」的直接原因。
        def _sync_inner_width(event):
            canvas.itemconfigure(window_id, width=event.width)
        canvas.bind('<Configure>', _sync_inner_width)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 0))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 鼠标滚轮支持：仅在指针位于侧边栏内时生效，
        # 避免抢占右侧云图画布的 <MouseWheel> 缩放事件。
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        
        # 内容内边距
        inner_frame = tk.Frame(scrollable_frame, bg=self._pal('panel'))
        self._register(inner_frame, bg='panel')
        inner_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # === 时间与卫星 ===
        self._create_section_header(inner_frame, "时间与卫星")

        # 日期时间标签
        self._field_label(inner_frame, "日期时间 (UTC)", margin_top=8)

        # 年月日行
        date_frame = tk.Frame(inner_frame, bg=self._pal('panel'))
        self._register(date_frame, bg='panel')
        date_frame.pack(fill=tk.X)

        # 年
        year_frame = tk.Frame(date_frame, bg=self._pal('panel'))
        self._register(year_frame, bg='panel')
        year_frame.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        self.year_var = tk.StringVar()
        # utcnow() 自 Python 3.12 起弃用且返回 naive datetime，
        # 改用带 tzinfo 的 now(timezone.utc)，避免与后续 UTC 时间换算混淆。
        today = datetime.datetime.now(datetime.timezone.utc)
        year_list = [str(y) for y in range(2015, today.year + 1)]
        # 必须显式给 width：ttk.Combobox 默认按 20 个字符索要约 175px，
        # 年月日三个并排就是 525px，而侧栏可用宽度只有约 255px。pack 不会把控件
        # 压到请求宽度以下，结果最后打包的「日」被挤出可视区、winfo_ismapped()=0，
        # 用户根本点不到它（表现为"选不了日期"）。改小自然宽度后由 expand 均分剩余空间。
        self.year_combo = ttk.Combobox(year_frame, textvariable=self.year_var,
                                        values=year_list, width=6,
                                        state='readonly', style='Dark.TCombobox')
        self.year_combo.pack(fill=tk.X)
        self.year_var.set(str(today.year))
        self.year_combo.bind('<<ComboboxSelected>>', self._update_days)
        
        # 月
        month_frame = tk.Frame(date_frame, bg=self._pal('panel'))
        self._register(month_frame, bg='panel')
        month_frame.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
        self.month_var = tk.StringVar()
        month_list = [f"{m:02d}" for m in range(1, 13)]
        self.month_combo = ttk.Combobox(month_frame, textvariable=self.month_var,
                                         values=month_list, width=3,
                                         state='readonly', style='Dark.TCombobox')
        self.month_combo.pack(fill=tk.X)
        self.month_var.set(f"{today.month:02d}")
        self.month_combo.bind('<<ComboboxSelected>>', self._update_days)
        
        # 日
        day_frame = tk.Frame(date_frame, bg=self._pal('panel'))
        self._register(day_frame, bg='panel')
        day_frame.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))
        self.day_var = tk.StringVar()
        self.day_combo = ttk.Combobox(day_frame, textvariable=self.day_var,
                                       width=3, state='readonly',
                                       style='Dark.TCombobox')
        self.day_combo.pack(fill=tk.X)
        self._update_days()

        # 时间选择
        self._field_label(inner_frame, "时次")

        self.time_var = tk.StringVar()
        time_list = [f"{h:02d}:00:00" for h in range(24)]
        self.time_combo = ttk.Combobox(inner_frame, textvariable=self.time_var,
                                        values=time_list,
                                        state='readonly', style='Dark.TCombobox')
        self.time_combo.pack(fill=tk.X)
        self.time_var.set("09:00:00")
        
        # 卫星选择
        self._field_label(inner_frame, "卫星平台")

        self.platform_var = tk.StringVar(value='Himawari-9')
        self.platform_combo = ttk.Combobox(
            inner_frame,
            textvariable=self.platform_var,
            values=PLATFORM_OPTIONS,
            state='readonly',
            style='Dark.TCombobox',
        )
        self.platform_combo.pack(fill=tk.X)
        self.platform_combo.bind('<<ComboboxSelected>>', self._on_platform_change)
        
        # 观测区域
        self._field_label(inner_frame, "观测区域")

        self.region_var = tk.StringVar(value='F')
        self.region_combo = ttk.Combobox(inner_frame, textvariable=self.region_var,
                                         state='readonly', style='Dark.TCombobox')
        self.region_combo.pack(fill=tk.X)
        self.region_combo['values'] = ('F (全圆盘)', 'T (目标区域/机动观测)')
        self.region_var.set('F (全圆盘)')
        
        # === 数据与显示 ===
        self._create_section_header(inner_frame, "数据与显示", margin_top=20)

        # 数据类型
        self._field_label(inner_frame, "数据类型", margin_top=8)

        self.data_type_var = tk.StringVar(value='IR')
        type_display = [f"{k} ({v['name']})" for k, v in DATA_TYPES.items()]
        type_combo = ttk.Combobox(inner_frame, textvariable=self.data_type_var,
                                   values=type_display,
                                   style='Dark.TCombobox')
        type_combo.pack(fill=tk.X)
        type_combo.bind('<<ComboboxSelected>>', self._on_type_change)
        type_combo.set('IR (红外窗区)')
        
        # 波段
        self._field_label(inner_frame, "波段")

        self.band_var = tk.StringVar()
        self.band_combo = ttk.Combobox(inner_frame, textvariable=self.band_var,
                                         values=DATA_TYPES['IR']['bands'],
                                         style='Dark.TCombobox')
        self.band_combo.pack(fill=tk.X)
        self.band_var.set(DATA_TYPES['IR']['default_band'])
        
        # 色阶方案
        self._field_label(inner_frame, "色阶方案")

        self.scheme_var = tk.StringVar()
        self.scheme_combo = ttk.Combobox(inner_frame, textvariable=self.scheme_var,
                                          values=DATA_TYPES['IR']['schemes'],
                                          style='Dark.TCombobox')
        self.scheme_combo.pack(fill=tk.X)
        self.scheme_var.set(DATA_TYPES['IR']['default_scheme'])
        
        # === 操作按钮 ===
        self._create_section_header(inner_frame, "操作", margin_top=20)

        # 主操作按钮
        btn_container = tk.Frame(inner_frame, bg=self._pal('panel'))
        self._register(btn_container, bg='panel')
        btn_container.pack(fill=tk.X, pady=(8, 0))

        self.draw_btn = ttk.Button(btn_container, text="绘制云图", command=self._draw_image,
                                   style='Primary.TButton')
        self.draw_btn.pack(fill=tk.X, pady=(0, 8))

        # 次要按钮行
        secondary_btn_frame = tk.Frame(inner_frame, bg=self._pal('panel'))
        self._register(secondary_btn_frame, bg='panel')
        secondary_btn_frame.pack(fill=tk.X)
        
        self.save_btn = ttk.Button(secondary_btn_frame, text="保存图片", command=self._save_image,
                                   state=tk.DISABLED, style='Secondary.TButton')
        self.save_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))
        
        self.clear_btn = ttk.Button(secondary_btn_frame, text="清空", command=self._clear_image,
                                    style='Danger.TButton')
        self.clear_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6, 0))
        
        # === 进度状态 ===
        self._create_section_header(inner_frame, "状态", margin_top=20)

        progress_card = tk.Frame(inner_frame, bg=self._pal('surface'),
                                 highlightbackground=self._pal('border'),
                                 highlightthickness=1)
        self._register(progress_card, bg='surface', highlightbackground='border')
        progress_card.pack(fill=tk.X, pady=(8, 0))

        self.progress_var = tk.StringVar(value="就绪")
        self.progress_label = tk.Label(progress_card, textvariable=self.progress_var,
                                       bg=self._pal('surface'), fg=self._pal('text_subtle'),
                                       font=self._font('body'),
                                       anchor=tk.W, padx=12, pady=8)
        self._register(self.progress_label, bg='surface', fg='text_subtle')
        self._font_widgets.append((self.progress_label, 'body', False))
        self.progress_label.pack(fill=tk.X)
        
        self.download_progress = ttk.Progressbar(progress_card, mode='determinate',
                                                  maximum=1, value=0,
                                                  style='Dark.Horizontal.TProgressbar')
        self.download_progress.pack(fill=tk.X, padx=12, pady=(0, 12))

    def _create_section_header(self, parent, text, margin_top=0):
        """创建分区标题（带下划线）"""
        frame = tk.Frame(parent, bg=self._pal('panel'))
        self._register(frame, bg='panel')
        frame.pack(fill=tk.X, pady=(margin_top, 0))

        label = tk.Label(frame, text=text,
                         bg=self._pal('panel'), fg=self._pal('text_muted'),
                         font=self._font('heading', bold=True))
        self._register(label, bg='panel', fg='text_muted')
        # 分区标题随字号档位重设字体，登记到可重构列表
        self._font_widgets.append((label, 'heading', True))
        label.pack(anchor=tk.W)

        # 下划线：必须挂在 frame 内部，否则会被 pack 到 parent 的最末尾，
        # 导致下划线出现在所有同级控件之后而非紧贴标题下方。
        line = tk.Frame(frame, bg=self._pal('hover'), height=1)
        self._register(line, bg='hover')
        line.pack(fill=tk.X, pady=(8, 0))

    def _create_image_view(self, parent):
        """创建中间图像区（工具条 + 画布 + 进度条）"""
        view_frame = tk.Frame(parent, bg=self._pal('window'))
        self._register(view_frame, bg='window')
        view_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 工具条：高度由内容决定（不再 height=40 + pack_propagate(False)），
        # 左右两组之间放 expand spacer，保证任何宽度都不重叠。
        toolbar = tk.Frame(view_frame, bg=self._pal('panel'))
        self._register(toolbar, bg='panel')
        toolbar.pack(fill=tk.X, side=tk.TOP)
        self._hairline(toolbar, tk.BOTTOM)

        toolbar_row = tk.Frame(toolbar, bg=self._pal('panel'))
        self._register(toolbar_row, bg='panel')
        toolbar_row.pack(fill=tk.X, padx=12, pady=7)

        # 右侧：提示文字（最先 pack RIGHT，天然贴右）
        toolbar_right = tk.Frame(toolbar_row, bg=self._pal('panel'))
        self._register(toolbar_right, bg='panel')
        toolbar_right.pack(side=tk.RIGHT)

        self.tip_label = tk.Label(toolbar_right, text="滚轮缩放 · 拖拽平移",
                                  bg=self._pal('panel'), fg=self._pal('text_subtle'),
                                  font=self._font('caption'))
        self._register(self.tip_label, bg='panel', fg='text_subtle')
        self._font_widgets.append((self.tip_label, 'caption', False))
        self.tip_label.pack(side=tk.RIGHT)
        # 窄窗时提示语是最次要信息，与版本号一起隐藏，优先保住标题与缩放读数
        self._responsive_extras = getattr(self, '_responsive_extras', [])
        self._responsive_extras.append((self.tip_label, {'side': tk.RIGHT}))

        # 左侧：标题 + 缩放读数
        toolbar_left = tk.Frame(toolbar_row, bg=self._pal('panel'))
        self._register(toolbar_left, bg='panel')
        toolbar_left.pack(side=tk.LEFT)

        stage_title = tk.Label(toolbar_left, text="图像画布",
                               bg=self._pal('panel'), fg=self._pal('text_secondary'),
                               font=self._font('body'))
        self._register(stage_title, bg='panel', fg='text_secondary')
        self._font_widgets.append((stage_title, 'body', False))
        stage_title.pack(side=tk.LEFT, padx=(0, 10))

        self.zoom_var = tk.StringVar(value="100%")
        zoom_label = tk.Label(toolbar_left, textvariable=self.zoom_var,
                              bg=self._pal('hover'), fg=self._pal('text_muted'),
                              font=self._font('caption'),
                              padx=8, pady=3)
        self._register(zoom_label, bg='hover', fg='text_muted')
        self._font_widgets.append((zoom_label, 'caption', False))
        zoom_label.pack(side=tk.LEFT)

        # 弹性垫：中栏变窄时先压缩它，两侧文字永不互相覆盖
        self._toolbar_spacer = tk.Frame(toolbar_row, bg=self._pal('panel'))
        self._register(self._toolbar_spacer, bg='panel')
        self._toolbar_spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 图像画布容器：底色跟随主题，figure 内部始终黑底（云图本体不变）
        self.stage_container = tk.Frame(view_frame, bg=self._pal('stage'))
        self._register(self.stage_container, bg='stage')
        self.stage_container.pack(fill=tk.BOTH, expand=True)

        # 创建 matplotlib 画布
        # figsize 不再写死 (8,6)：FigureCanvasTkAgg 会随 pack 的可用空间伸缩，
        # 但初始 figure 尺寸影响首次布局，这里给一个与默认窗口接近的比值。
        self.fig, self.ax = plt.subplots(figsize=(8, 6), dpi=100)
        self.fig.patch.set_facecolor(FIGURE_BG)
        self.ax.set_axis_off()
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.stage_container)
        # 画布内边距随窗口宽度变化，窄窗时收紧，避免画布被 padding 挤没
        self._canvas_pad = 16
        self._canvas_widget = self.canvas.get_tk_widget()
        self._canvas_widget.pack(fill=tk.BOTH, expand=True,
                                 padx=self._canvas_pad,
                                 pady=self._canvas_pad)

        # 底部进度条（贴住工具条对称位置）
        progress_strip = tk.Frame(view_frame, bg=self._pal('panel'), height=3)
        self._register(progress_strip, bg='panel')
        progress_strip.pack(fill=tk.X, side=tk.BOTTOM)
        progress_strip.pack_propagate(False)

    def _create_layer_rail(self, parent):
        """创建右侧图层栏：图层开关 + 色彩映射 + 输出队列。

        宽度由 RAIL_TIERS 档位决定（不再写死 264），窄窗时收窄，
        给中间图像区留出空间，避免画布被挤成窄条。
        """
        _, _, right_width, _ = _tier_for(self._layout_width or 1280, RAIL_TIERS)
        rail = tk.Frame(parent, bg=self._pal('panel'), width=right_width)
        self._register(rail, bg='panel')
        rail.pack(side=tk.RIGHT, fill=tk.Y)
        rail.pack_propagate(False)
        self._rail = rail

        # 左侧分隔线
        self._hairline(rail, tk.LEFT)

        inner = tk.Frame(rail, bg=self._pal('panel'))
        self._register(inner, bg='panel')
        inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        self._rail_inner = inner

        # === 图层 ===
        self._create_section_header(inner, "图层")

        self.layer_vars = {}
        layers = (
            ('ir_window', '红外窗区', True),
            ('water_vapor', '水汽通道', False),
            ('graticule', '经纬网', True),
            ('coastline', '海岸线', True),
            ('track', '路径追踪', False),
        )
        for key, label_text, default in layers:
            var = tk.BooleanVar(value=default)
            self.layer_vars[key] = var
            row = tk.Frame(inner, bg=self._pal('panel'))
            self._register(row, bg='panel')
            row.pack(fill=tk.X, pady=(8, 0))
            check = tk.Checkbutton(row, text=label_text, variable=var,
                                   bg=self._pal('panel'), fg=self._pal('text_secondary'),
                                   activebackground=self._pal('panel'),
                                   activeforeground=self._pal('text'),
                                   selectcolor=self._pal('input'),
                                   highlightthickness=0, bd=0,
                                   font=self._font('body'), anchor=tk.W)
            self._register(check, bg='panel', fg='text_secondary',
                           activebackground='panel', activeforeground='text',
                           selectcolor='input')
            self._font_widgets.append((check, 'body', False))
            check.pack(side=tk.LEFT)

        # === 色彩映射 ===
        self._create_section_header(inner, "色彩映射", margin_top=20)

        self._field_label(inner, "色阶", margin_top=8)
        self.ramp_var = tk.StringVar(value='IR 标准')
        self.ramp_combo = ttk.Combobox(inner, textvariable=self.ramp_var,
                                       values=('IR 标准', '增强对比', '灰度',
                                               '水汽暖色', '单色'),
                                       state='readonly', style='Dark.TCombobox')
        self.ramp_combo.pack(fill=tk.X)

        self._field_label(inner, "温度范围 (℃)")
        range_row = tk.Frame(inner, bg=self._pal('panel'))
        self._register(range_row, bg='panel')
        range_row.pack(fill=tk.X)

        self.vmin_var = tk.StringVar(value='-82')
        vmin_entry = tk.Entry(range_row, textvariable=self.vmin_var, width=6,
                              bg=self._pal('input'), fg=self._pal('text'),
                              insertbackground=self._pal('text'),
                              relief='flat', highlightthickness=1,
                              highlightbackground=self._pal('border'),
                              highlightcolor=self._pal('border_focus'),
                              font=self._font('body'))
        self._register(vmin_entry, bg='input', fg='text', insertbackground='text',
                       highlightbackground='border', highlightcolor='border_focus')
        self._font_widgets.append((vmin_entry, 'body', False))
        vmin_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        sep = tk.Label(range_row, text="~", bg=self._pal('panel'),
                       fg=self._pal('text_subtle'), font=self._font('body'))
        self._register(sep, bg='panel', fg='text_subtle')
        sep.pack(side=tk.LEFT, padx=6)

        self.vmax_var = tk.StringVar(value='32')
        vmax_entry = tk.Entry(range_row, textvariable=self.vmax_var, width=6,
                              bg=self._pal('input'), fg=self._pal('text'),
                              insertbackground=self._pal('text'),
                              relief='flat', highlightthickness=1,
                              highlightbackground=self._pal('border'),
                              highlightcolor=self._pal('border_focus'),
                              font=self._font('body'))
        self._register(vmax_entry, bg='input', fg='text', insertbackground='text',
                       highlightbackground='border', highlightcolor='border_focus')
        self._font_widgets.append((vmax_entry, 'body', False))
        vmax_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 色带预览 + 两端刻度
        self.ramp_canvas = tk.Canvas(inner, height=10, highlightthickness=0,
                                     bg=self._pal('panel'))
        self._register_canvas(self.ramp_canvas, bg='panel')
        self.ramp_canvas.pack(fill=tk.X, pady=(10, 4))
        inner.bind('<Configure>', self._paint_ramp_preview)

        tick_row = tk.Frame(inner, bg=self._pal('panel'))
        self._register(tick_row, bg='panel')
        tick_row.pack(fill=tk.X)
        tick_left = tk.Label(tick_row, text="-82", bg=self._pal('panel'),
                             fg=self._pal('text_subtle'), font=self._font('micro'))
        self._register(tick_left, bg='panel', fg='text_subtle')
        self._font_widgets.append((tick_left, 'micro', False))
        tick_left.pack(side=tk.LEFT)
        tick_right = tk.Label(tick_row, text="32", bg=self._pal('panel'),
                              fg=self._pal('text_subtle'), font=self._font('micro'))
        self._register(tick_right, bg='panel', fg='text_subtle')
        self._font_widgets.append((tick_right, 'micro', False))
        tick_right.pack(side=tk.RIGHT)

        # 反转 / 等值线
        self.reverse_var = tk.BooleanVar(value=False)
        reverse_check = tk.Checkbutton(inner, text="反转色阶",
                                       variable=self.reverse_var,
                                       bg=self._pal('panel'), fg=self._pal('text_secondary'),
                                       activebackground=self._pal('panel'),
                                       activeforeground=self._pal('text'),
                                       selectcolor=self._pal('input'),
                                       highlightthickness=0, bd=0,
                                       font=self._font('body'), anchor=tk.W)
        self._register(reverse_check, bg='panel', fg='text_secondary',
                       activebackground='panel', activeforeground='text',
                       selectcolor='input')
        self._font_widgets.append((reverse_check, 'body', False))
        reverse_check.pack(anchor=tk.W, pady=(10, 0))

        self.contour_var = tk.BooleanVar(value=False)
        contour_check = tk.Checkbutton(inner, text="等值线叠加",
                                       variable=self.contour_var,
                                       bg=self._pal('panel'), fg=self._pal('text_secondary'),
                                       activebackground=self._pal('panel'),
                                       activeforeground=self._pal('text'),
                                       selectcolor=self._pal('input'),
                                       highlightthickness=0, bd=0,
                                       font=self._font('body'), anchor=tk.W)
        self._register(contour_check, bg='panel', fg='text_secondary',
                       activebackground='panel', activeforeground='text',
                       selectcolor='input')
        self._font_widgets.append((contour_check, 'body', False))
        contour_check.pack(anchor=tk.W, pady=(6, 0))

        # === 输出队列 ===
        self._create_section_header(inner, "输出队列", margin_top=20)

        self.queue_labels = []
        for index in range(3):
            card = tk.Frame(inner, bg=self._pal('surface'),
                            highlightbackground=self._pal('border'),
                            highlightthickness=1)
            self._register(card, bg='surface', highlightbackground='border')
            card.pack(fill=tk.X, pady=(8, 0))
            text = tk.Label(card, text="—", bg=self._pal('surface'),
                            fg=self._pal('text_subtle'), font=self._font('caption'),
                            anchor=tk.W, padx=10, pady=6)
            self._register(text, bg='surface', fg='text_subtle')
            self._font_widgets.append((text, 'caption', False))
            text.pack(fill=tk.X)
            self.queue_labels.append(text)

    def _paint_ramp_preview(self, event=None):
        """重绘色带预览：canvas 图形项不随主题变色，必须整体重建。"""
        canvas = getattr(self, 'ramp_canvas', None)
        if canvas is None:
            return
        canvas.delete('all')
        width = canvas.winfo_width()
        if width <= 1:
            return
        steps = 48
        # 红外窗区标准色阶的粗粒度镜像（暗→亮 = 冷→暖）
        stops = ('#0b1020', '#3b0764', '#7e22ce', '#b91c1c',
                 '#f97316', '#fde047', '#f8fafc')
        for index in range(steps):
            position = index / (steps - 1)
            scaled = position * (len(stops) - 1)
            low = int(scaled)
            high = min(low + 1, len(stops) - 1)
            mix = scaled - low
            color = _blend_hex(stops[low], stops[high], mix)
            x0 = width * index / steps
            x1 = width * (index + 1) / steps
            canvas.create_rectangle(x0, 0, x1, 10, fill=color, outline='')

    def _create_status_bar(self, parent):
        """创建底部状态栏：左状态 + 中时间轴刻度 + 右队列信息。

        早期版本用 height=32 + pack_propagate(False) 锁死高度，字号一放大
        文字就被纵向切掉；左右两组之间也没有弹性垫，缩窗时直接压盖。
        这里改为「内容决定高度 + 中间弹性垫 + 窄窗隐藏次要信息」。
        """
        status_bar = tk.Frame(parent, bg=self._pal('panel'))
        self._register(status_bar, bg='panel')
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self._status_bar = status_bar

        # 顶部分隔线（必须最先 pack TOP，才贴得住上沿）
        self._hairline(status_bar, tk.TOP)

        row = tk.Frame(status_bar, bg=self._pal('panel'))
        self._register(row, bg='panel')
        row.pack(fill=tk.X, padx=16, pady=5)

        # 右侧信息（先 pack RIGHT，天然贴右）
        right_frame = tk.Frame(row, bg=self._pal('panel'))
        self._register(right_frame, bg='panel')
        right_frame.pack(side=tk.RIGHT)

        self._status_right_label = tk.Label(right_frame, text="S3 数据源",
                                            bg=self._pal('panel'),
                                            fg=self._pal('text_subtle'),
                                            font=self._font('micro'))
        self._register(self._status_right_label, bg='panel', fg='text_subtle')
        self._font_widgets.append((self._status_right_label, 'micro', False))
        self._status_right_label.pack(side=tk.RIGHT)

        # 左侧状态
        left_frame = tk.Frame(row, bg=self._pal('panel'))
        self._register(left_frame, bg='panel')
        left_frame.pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="●  就绪")
        self.status_label = tk.Label(left_frame, textvariable=self.status_var,
                                     bg=self._pal('panel'), fg=self._pal('text_subtle'),
                                     font=self._font('caption'))
        self._register(self.status_label, bg='panel', fg='text_subtle')
        self._font_widgets.append((self.status_label, 'caption', False))
        self.status_label.pack(side=tk.LEFT)

        self._status_source_label = tk.Label(left_frame, text="s3://noaa-himawari9",
                                             bg=self._pal('panel'),
                                             fg=self._pal('text_subtle'),
                                             font=self._font('micro'))
        self._register(self._status_source_label, bg='panel', fg='text_subtle')
        self._font_widgets.append((self._status_source_label, 'micro', False))
        self._status_source_label.pack(side=tk.LEFT, padx=(12, 0))
        # 「S3 数据源」与桶地址在窄窗下隐藏：它们只是装饰性信息，
        # 保留它们会把 12 个刻度挤到 0 宽，视觉上像一条重叠的色块。
        self._responsive_extras = getattr(self, '_responsive_extras', [])
        self._responsive_extras.extend((
            (self._status_right_label, {'side': tk.RIGHT}),
            (self._status_source_label, {'side': tk.LEFT, 'padx': (12, 0)}),
        ))

        # 中间时间轴：12 个时次刻度（两侧 padx 固定，由 expand 吸收剩余空间）
        timeline = tk.Frame(row, bg=self._pal('panel'))
        self._register(timeline, bg='panel')
        timeline.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=24)
        self._timeline = timeline

        self.timeline_ticks = []
        # 刻度用「单 Canvas 画 12 组（点 + 小时数字）」而不是 12 个 Canvas 控件：
        # 12 个独立 Canvas 各自带 highlight 边框 + 独立宽度，视觉上会串成一排方框；
        # 单画布在 <Configure> 里等分重绘，永远整齐。
        self._timeline_canvas = tk.Canvas(timeline, height=22, highlightthickness=0,
                                          bd=0, bg=self._pal('panel'))
        self._register_canvas(self._timeline_canvas, bg='panel', line='primary')
        self._timeline_canvas.pack(fill=tk.X, expand=True)
        self._timeline_canvas.bind('<Configure>', self._paint_timeline)
        for hour in (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22):
            self.timeline_ticks.append((self._timeline_canvas, hour))

    def _paint_timeline(self, event=None):
        """重绘整条时间轴：12 个等分刻度（圆点 + 小时数字），当前时次高亮。"""
        canvas = getattr(self, '_timeline_canvas', None)
        if canvas is None:
            return
        canvas.delete('all')
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            return
        step = width / 12.0
        now_hour = datetime.datetime.now(datetime.timezone.utc).hour
        # 画布 22px 高：圆点占 y=2..8，数字从 y=9 起 anchor='n'，底部留 1px 余量，
        # 避免数字下沿被窗口底边裁掉（状态栏总高只有约 34px）。
        dot_y = 2
        for index, hour in enumerate(range(0, 24, 2)):
            cx = step * (index + 0.5)
            current = hour == (now_hour // 2) * 2
            past = hour <= now_hour
            if current:
                canvas.create_oval(cx - 3.5, dot_y - 1, cx + 3.5, dot_y + 5,
                                   fill=self._pal('primary'),
                                   outline=self._pal('primary'), width=0)
            else:
                canvas.create_oval(cx - 2.5, dot_y, cx + 2.5, dot_y + 4,
                                   fill='',
                                   outline=self._pal('primary') if past
                                   else self._pal('border_strong'),
                                   width=2 if past else 1)
            canvas.create_text(cx, dot_y + 8, text=f"{hour:02d}",
                               fill=self._pal('text') if current else self._pal('text_subtle'),
                               font=self._font('micro'),
                               anchor='n')

    def _paint_tick(self, tick, hour):
        """兼容单刻度重绘入口：转交整条时间轴重绘（刻度已合并到单画布）。"""
        self._paint_timeline()

    def _update_days(self, event=None):
        """根据年月更新日期选项"""
        try:
            year = int(self.year_var.get())
            month = int(self.month_var.get())
            if month == 2:
                if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
                    days = 29
                else:
                    days = 28
            elif month in [4, 6, 9, 11]:
                days = 30
            else:
                days = 31
            day_list = [f"{d:02d}" for d in range(1, days + 1)]
            self.day_combo['values'] = day_list
            
            current_day = int(self.day_var.get() if self.day_var.get() else 1)
            if current_day > days:
                self.day_var.set(f"{days:02d}")
            elif not self.day_var.get():
                self.day_var.set("01")
        except ValueError:
            pass
        
    def _on_platform_change(self, event):
        """卫星改变时同步其可用区域、日期和分钟时次。"""
        platform = _platform_identifier(self.platform_var.get())
        config = get_provider_config(platform)
        self.region_combo['values'] = tuple(
            'F (全圆盘)' if region == 'F' else 'T (目标区域/机动观测)'
            for region in config.regions
        )
        self.region_combo.config(state='readonly')
        self.region_var.set('F (全圆盘)' if 'F' in config.regions else self.region_combo['values'][0])

        archive_start, archive_end = get_archive_window(platform)
        if archive_start is not None or archive_end is not None:
            requested_date = datetime.date(
                int(self.year_var.get()), int(self.month_var.get()), int(self.day_var.get())
            )
            bounded_date = requested_date
            if archive_start is not None and bounded_date < archive_start:
                bounded_date = archive_start
            if archive_end is not None and bounded_date > archive_end:
                bounded_date = archive_end
            if bounded_date != requested_date:
                self.year_var.set(f'{bounded_date.year:04d}')
                self.month_var.set(f'{bounded_date.month:02d}')
                self.day_var.set(f'{bounded_date.day:02d}')
                self._update_days()

        hour, minute = (int(value) for value in self.time_var.get().split(':', 2)[:2])
        time_values = getattr(self.time_combo, 'values', ())
        if config.minutes == (0,):
            time_values = tuple(f"{value:02d}:00:00" for value in range(24))
            self.time_combo['values'] = time_values
            self.time_var.set(f"{hour:02d}:00:00")
        else:
            time_values = tuple(
                f"{value_hour:02d}:{value_minute:02d}:00"
                for value_hour in range(24)
                for value_minute in config.minutes
            )
            self.time_combo['values'] = time_values
            selected_minute = minute if minute in config.minutes else config.minutes[0]
            self.time_var.set(f"{hour:02d}:{selected_minute:02d}:00")
        self.data_type_var.set('IR (红外窗区)')
        self._on_type_change(None)

    def _on_type_change(self, event):
        """数据类型改变时更新波段和色阶列表"""
        display = self.data_type_var.get()
        data_type = display.split(' ')[0]
        
        bands = DATA_TYPES[data_type]['bands']
        self.band_combo['values'] = bands
        self.band_var.set(DATA_TYPES[data_type]['default_band'])
        
        schemes = DATA_TYPES[data_type]['schemes']
        self.scheme_combo['values'] = schemes
        self.scheme_var.set(DATA_TYPES[data_type]['default_scheme'])
        
    def _draw_image(self):
        """绘制云图（在后台线程中执行）"""
        year = self.year_var.get()
        month = self.month_var.get()
        day = self.day_var.get()
        time_str = self.time_var.get()
        platform = _platform_identifier(self.platform_var.get())
        display = self.data_type_var.get()
        data_type = display.split(' ')[0]
        band = self.band_var.get()
        scheme = self.scheme_var.get()
        
        region_display = self.region_var.get()
        region = 'F' if region_display.startswith('F') else 'T'
        
        try:
            date_str = f"{year}-{month}-{day}"
            full_time = f"{date_str}T{time_str}"
            datetime.datetime.strptime(full_time, '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            self._show_error_dialog("日期时间错误", "日期时间格式不正确！")
            return

        provider_config = get_provider_config(platform)
        if (
            provider_config.minutes != (0,)
            and int(time_str.split(':')[1]) not in provider_config.minutes
        ):
            self._show_error_dialog(
                "日期时间错误",
                "GOES 全圆盘仅提供每 10 分钟一个时次，请选择 00、10、20、30、40 或 50 分钟。",
            )
            return
        
        self._next_task_id += 1
        task_id = self._next_task_id
        self._active_task_id = task_id
        # 标记有任务在飞：关窗时据此确认，避免"正在下载却被静默中断"
        self._draw_in_flight = True
        self.draw_btn.config(state=tk.DISABLED)
        self._show_status_feedback('Working', f"正在下载 {DATA_TYPES[data_type]['name']} {band} 数据...")
        self.status_var.set("⏳  正在下载数据...")
        self.root.update()
        
        thread = threading.Thread(target=self._draw_worker, 
                                  args=(task_id, full_time, scheme, region, data_type, band, platform))
        thread.daemon = True
        thread.start()
        
    def _draw_worker(self, task_id, time_str, scheme, region, data_type, band, platform='Himawari-9'):
        """后台绘制工作线程"""
        try:
            def report_download_progress(downloaded_bytes, total_bytes, file_index, file_count):
                self._enqueue_ui_call(
                    self._set_download_progress,
                    task_id,
                    downloaded_bytes,
                    total_bytes,
                    file_index,
                    file_count,
                )

            out_path, data, extent = draw_ir_fulldisk(
                time_str=time_str, scheme=scheme, region=region,
                data_type=data_type, band=band, add_decorations=True,
                progress_callback=report_download_progress, platform=platform,
            )
            self._enqueue_ui_call(self._on_draw_success, task_id, out_path, data, extent, scheme)

        except Exception as e:
            error_str = str(e)
            if "No CMIPF scan" in error_str or isinstance(e, FileNotFoundError):
                error_msg = (
                    "所选 UTC 时次没有可用的 GOES 全圆盘数据。请确认卫星和时间，或选择相邻的 10 分钟时次。"
                    f"\n\n{error_str}"
                )
            elif "unrecognized engine 'h5netcdf'" in error_str:
                error_msg = (
                    "缺少 GOES NetCDF 读取组件 h5netcdf。当前 Python 环境缺少 h5netcdf。\n\n"
                    "请关闭本窗口后，使用项目虚拟环境启动：\n"
                    ".venv\\Scripts\\python.exe himawari_ir_toolkit\\himawari_gui.py\n\n"
                    "如项目虚拟环境尚未安装依赖，请执行：\n"
                    "python -m pip install -r requirements.txt\n\n"
                    f"诊断信息：\n{error_str}"
                )
            elif "No data found" in error_str:
                if region == 'T':
                    region_tip = "\n⚠ 目标区域（Target）早期数据可能不完整，建议使用全圆盘（FLDK）查看历史数据"
                else:
                    region_tip = ""
                error_msg = f"数据不可用\n\n{error_str}\n\n建议：\n1. 尝试选择较新的时间（如近几个月）\n2. 检查是否选择了正确的波段\n3. Himawari数据按小时提供，请选择整点时间\n4. 早期数据（2015-2018年）可能不完整{region_tip}"
            else:
                error_msg = f"{error_str}\n\n{traceback.format_exc()}"
            self._enqueue_ui_call(self._on_draw_error, task_id, error_msg)
            
        finally:
            self._enqueue_ui_call(self._set_draw_button_state, task_id, tk.NORMAL)

    def _enqueue_ui_call(self, callback, *args, **kwargs):
        """将 UI 更新切回主线程执行。"""
        self.ui_queue.put((callback, args, kwargs))

    def _process_ui_queue(self):
        """在主线程中依次执行后台线程投递的 UI 更新。

        这是全程序唯一的 UI 更新通道，靠每 50ms 自调度续命。一旦某个回调抛异常
        把 `after` 顶掉，泵就永久停摆：之后下载进度、成功回调、失败弹窗全部静默
        失效，界面表现为「按钮一直灰着、状态栏停在正在下载」。所以这里必须做到：
        1. 取任务只认 get_nowait 的 queue.Empty，不用 empty() 判空（有竞态）；
        2. 每个回调独立 try/except，一个坏回调不能连累后面的；
        3. 留痕本身也要容错（打包成窗口程序时 sys.stderr 可能是 None）；
        4. 无论本轮是否出过异常，都必须重新 after 续排。
        """
        while True:
            try:
                callback, args, kwargs = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            # 单个回调失败只吞掉自己，泵继续跑
            try:
                callback(*args, **kwargs)
            except Exception:
                try:
                    traceback.print_exc()
                except Exception:
                    # sys.stderr 为 None 时 print_exc 会再抛，留痕不能再把泵带崩
                    pass
        # 关窗流程已启动就不再续排：否则 after 会在窗口销毁后触发，
        # Tk 报 bgerror "invalid command name ..._process_ui_queue"。
        self._pump_after_id = None
        if getattr(self, '_closing', False):
            return
        try:
            self._pump_after_id = self.root.after(50, self._process_ui_queue)
        except tk.TclError:
            # 窗口正在销毁时 after 会抛，此时泵自然终止
            self._pump_after_id = None

    def _cancel_pending_callbacks(self):
        """取消所有挂起的 after，避免窗口销毁后仍有回调被触发。

        Tk 在窗口销毁时会连对应 Tcl 命令一起删掉，此时若还有 pending 的 after
        指向它，触发时就会抛 bgerror "invalid command name ..."，表现为退出时
        控制台/日志里冒出一串看着像崩溃的噪音。
        """
        for attr in ('_pump_after_id', '_resize_after_id', 'zoom_after_id',
                     '_status_feedback_after_id', '_initial_layout_after_id'):
            after_id = getattr(self, attr, None)
            if after_id is None:
                continue
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
            setattr(self, attr, None)

    def _cancel_matplotlib_callbacks(self):
        """取消 matplotlib TkAgg 画布挂起的 idle 重绘。

        FigureCanvasTk 用 after_idle 排队重绘（_idle_draw_id）并挂了一个事件循环
        回调（_event_loop_id）。窗口若在 after 回调里被销毁，这些 Tcl 命令已随销毁
        一起消失，idle 回调再触发就会报
        `bgerror ... invalid command name "...idle_draw"`，而且会让 mainloop 卡住
        不退出（关窗后进程残留）。官方 FigureManagerTk.destroy 也是这么取消的。
        """
        canvas = getattr(self, 'canvas', None)
        tkcanvas = getattr(canvas, '_tkcanvas', None)
        if tkcanvas is None:
            return
        for attr in ('_idle_draw_id', '_event_loop_id'):
            after_id = getattr(canvas, attr, None)
            if not after_id:
                continue
            try:
                tkcanvas.after_cancel(after_id)
            except tk.TclError:
                pass
            setattr(canvas, attr, None)

    def _on_close(self):
        """关窗统一出口：确认在飞任务 → 取消挂起的 after → 销毁窗口。

        没有这个出口时，点右上角关闭会直接销毁窗口，而工作线程仍在下载/绘图，
        且 UI 泵的 after 还挂着，于是退出噪音与半截文件同时出现。
        """
        if getattr(self, '_draw_in_flight', False) and not getattr(self, '_closing', False):
            try:
                confirmed = messagebox.askyesno(
                    "正在绘制",
                    "云图仍在下载或绘制中。现在退出会中断本次任务，"
                    "已开始但未写完的图片可能残留在 data 目录。\n\n确定退出吗？",
                    parent=self.root,
                )
            except tk.TclError:
                confirmed = True
            if not confirmed:
                return
        self._closing = True
        self._cancel_pending_callbacks()
        self._cancel_matplotlib_callbacks()
        # 先 quit 停掉事件循环再 destroy。只 destroy 时，若当前正处在 after 回调里，
        # mainloop 有可能不返回，表现为"窗口没了但进程还在"。
        try:
            self.root.quit()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _set_progress_text(self, text):
        self.progress_var.set(text)

    def _show_status_feedback(self, kind, message, duration=900):
        # 记住最后一次状态种类，切主题时按它重刷状态栏前景色
        self._status_kind = kind
        try:
            after_id = getattr(self, '_status_feedback_after_id', None)
            if after_id is not None:
                self.root.after_cancel(after_id)
            self.progress_var.set(message)
            self.progress_label.configure(fg=self._get_status_color(kind))

            def _reset_status_color():
                # 复原后状态种类也回到 Ready，避免下次切主题又刷成上一次的临时色
                self._status_kind = 'Ready'
                self.progress_label.configure(fg=self._get_status_color('Ready'))

            self._status_feedback_after_id = self.root.after(duration, _reset_status_color)
        except tk.TclError:
            pass

    def _get_status_color(self, kind):
        """状态文字配色，跟随当前主题的调色板令牌。"""
        # 测试会用 object.__new__ 造实例，可能没有 _theme，这里按浅色兜底
        theme = getattr(self, '_theme', 'light')
        pal = THEMES[theme]() if theme in THEMES else light_palette()
        colors = {
            'Working': pal['primary'],
            'Success': pal['success'],
            'Error': pal['error'],
            'Ready': pal['text_subtle'],
        }
        return colors.get(kind, pal['text_subtle'])

    def _set_download_progress(self, task_id, downloaded_bytes, total_bytes, file_index, file_count):
        if task_id != self._active_task_id:
            return
        if total_bytes:
            percent = downloaded_bytes / total_bytes * 100
            self.download_progress.config(maximum=total_bytes, value=downloaded_bytes)
            self.progress_var.set(
                f"下载中：第 {file_index}/{file_count} 个文件，{downloaded_bytes / 1024 / 1024:.1f} / "
                f"{total_bytes / 1024 / 1024:.1f} MB ({percent:.0f}%)"
            )
        else:
            self.download_progress.config(maximum=1, value=0)
            self.progress_var.set(f"查询文件大小：第 {file_index}/{file_count} 个文件")

    def _set_draw_button_state(self, task_id, state):
        # 这是工作线程 finally 里必投的信号，代表"后台线程已结束"这一事实本身。
        # 无论任务是否已失效（_clear_image 会把 _active_task_id 置 None）都要记录，
        # 否则关窗确认会一直以为还有任务在跑。
        self._draw_in_flight = False
        if task_id == self._active_task_id:
            self.draw_btn.config(state=state)

    def _on_draw_success(self, task_id, out_path, data, extent, scheme):
        if task_id != self._active_task_id:
            return
        self.current_image_path = out_path
        self.current_data = data
        self.current_extent = extent
        self.progress_var.set("正在显示云图...")
        self._display_image(data, scheme)
        self.download_progress.config(maximum=1, value=1)
        self.progress_var.set("绘制完成！")
        self._show_status_feedback('Success', "绘制完成！")
        self.status_var.set("✓  绘制完成")
        self.save_btn.config(state=tk.NORMAL)

    def _show_error_dialog(self, title, message):
        # 错误窗是经典 tk 控件，不参与 _register 回放，色值在构造时一次性取当前主题
        panel = self._pal('panel')
        text = self._pal('text')
        surface = self._pal('surface')
        # 去重：grab_set() 是模态独占，若已有错误窗持有 grab，
        # 再建第二个会抛 TclError("grab failed: another application has grab")，
        # 且旧窗口被新窗口遮住后用户无法关闭，形成假死。先销毁旧窗口。
        existing = getattr(self, '_error_dialog', None)
        if existing is not None:
            try:
                existing.destroy()
            except tk.TclError:
                pass
            self._error_dialog = None

        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        # 尺寸按屏幕可用区域的 60% 取，并夹在 [480, 960]×[360, 680]，
        # 避免在小屏上 800×560 超出可视区、在高分屏上又小得像邮票。
        screen_w = dialog.winfo_screenwidth()
        screen_h = dialog.winfo_screenheight()
        dlg_w = max(480, min(960, int(screen_w * 0.6)))
        dlg_h = max(360, min(680, int(screen_h * 0.6)))
        dialog.geometry(f"{dlg_w}x{dlg_h}")
        dialog.minsize(min(480, dlg_w), min(360, dlg_h))
        dialog.configure(bg=panel)
        dialog.transient(self.root)

        frame = tk.Frame(dialog, bg=panel, padx=16, pady=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text=title, bg=panel, fg=text,
                 font=self._font('heading', bold=True)).pack(anchor=tk.W, pady=(0, 12))

        text_frame = tk.Frame(frame, bg=panel)
        text_frame.pack(fill=tk.BOTH, expand=True)
        # 等宽字体保留堆栈可读性；字号走 body 档位，不再写死 10pt
        _, mono_size, _ = self._font('body')
        detail = tk.Text(text_frame, wrap=tk.WORD, undo=False,
                         font=('Consolas', mono_size),
                         bg=surface, fg=text, insertbackground=text,
                         relief='flat', borderwidth=0, padx=10, pady=10)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=detail.yview)
        detail.configure(yscrollcommand=scrollbar.set)
        detail.insert('1.0', message)
        detail.configure(state=tk.DISABLED)
        detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def select_all(_event=None):
            detail.configure(state=tk.NORMAL)
            detail.tag_add(tk.SEL, '1.0', tk.END)
            detail.mark_set(tk.INSERT, '1.0')
            detail.see(tk.INSERT)
            detail.configure(state=tk.DISABLED)
            return 'break'

        def copy_all():
            dialog.clipboard_clear()
            dialog.clipboard_append(message)

        detail.bind('<Control-a>', select_all)
        detail.bind('<Control-A>', select_all)
        buttons = tk.Frame(frame, bg=panel)
        buttons.pack(fill=tk.X, pady=(12, 0))
        
        def close_dialog():
            self._error_dialog = None
            dialog.destroy()

        ttk.Button(buttons, text="复制全部", command=copy_all,
                   style='Secondary.TButton').pack(side=tk.LEFT)
        ttk.Button(buttons, text="关闭", command=close_dialog,
                   style='Primary.TButton').pack(side=tk.RIGHT)
        
        dialog.protocol('WM_DELETE_WINDOW', close_dialog)
        # 窗口已完整构造完毕再夺取模态，避免构造中途异常留下悬挂 grab
        dialog.grab_set()
        self._error_dialog = dialog
        detail.focus_set()

    def _on_draw_error(self, task_id, error_msg):
        if task_id != self._active_task_id:
            return
        self._show_error_dialog("绘制失败", error_msg)
        self._show_status_feedback('Error', "绘制失败")
        self.status_var.set("✕  绘制失败")
            
    def _display_image(self, data, scheme):
        """使用PIL直接显示生成的图片文件"""
        from PIL import Image, ImageTk

        # 注意：不要 plt.close(self.fig)。figure 在 _create_image_view 中创建一次，
        # 生命周期与窗口一致；close 会让 self.ax / self.canvas 变成悬空引用，
        # 且 matplotlib global figure 管理器会因每次绘制新建 figure 而持续增长。
        # 此处只重置坐标轴即可。
        self.ax.clear()
        self.ax.set_axis_off()
        if self.original_img is not None:
            self.original_img.close()
        if self.current_resized_img is not None:
            self.current_resized_img.close()
        
        # 打开生成的图片文件
        self.original_img = Image.open(self.current_image_path)
        
        # 获取真正的Tkinter Canvas对象
        tk_canvas = self.canvas.get_tk_widget()
        
        # 计算初始居中位置
        canvas_width = tk_canvas.winfo_width()
        canvas_height = tk_canvas.winfo_height()
        img_width, img_height = self.original_img.size
        
        # 计算初始缩放比例（保持宽高比，居中显示）
        scale_width = canvas_width / img_width
        scale_height = canvas_height / img_height
        self.zoom_scale = min(scale_width, scale_height)
        
        # 计算居中偏移
        display_width = int(img_width * self.zoom_scale)
        display_height = int(img_height * self.zoom_scale)
        self.image_offset_x = (canvas_width - display_width) // 2
        self.image_offset_y = (canvas_height - display_height) // 2
        
        # 更新缩放显示
        self.zoom_var.set(f"{int(self.zoom_scale * 100)}%")
        
        # 绑定鼠标事件
        self._bind_mouse_events(tk_canvas)
        
        # 显示图片
        self._update_canvas_image()
    
    def _bind_mouse_events(self, tk_canvas):
        """绑定鼠标事件：滚轮缩放、左键拖拽"""
        tk_canvas.unbind('<MouseWheel>')
        tk_canvas.unbind('<ButtonPress-1>')
        tk_canvas.unbind('<B1-Motion>')
        tk_canvas.unbind('<ButtonRelease-1>')
        
        tk_canvas.bind('<MouseWheel>', self._on_mouse_wheel)
        tk_canvas.bind('<ButtonPress-1>', self._on_mouse_down)
        tk_canvas.bind('<B1-Motion>', self._on_mouse_drag)
        tk_canvas.bind('<ButtonRelease-1>', self._on_mouse_up)
    
    def _on_mouse_wheel(self, event):
        """鼠标滚轮缩放"""
        if self.original_img is None:
            return
        
        if event.delta > 0:
            zoom_factor = 1.15
        else:
            zoom_factor = 0.87
        
        new_scale = self.zoom_scale * zoom_factor
        new_scale = max(0.1, min(new_scale, 10.0))
        
        if new_scale == self.zoom_scale:
            return
        
        img_width, img_height = self.original_img.size
        old_display_width = int(img_width * self.zoom_scale)
        old_display_height = int(img_height * self.zoom_scale)
        
        mouse_x_ratio = (event.x - self.image_offset_x) / old_display_width if old_display_width > 0 else 0.5
        mouse_y_ratio = (event.y - self.image_offset_y) / old_display_height if old_display_height > 0 else 0.5
        
        self.zoom_scale = new_scale
        new_display_width = int(img_width * self.zoom_scale)
        new_display_height = int(img_height * self.zoom_scale)
        self.image_offset_x = event.x - int(mouse_x_ratio * new_display_width)
        self.image_offset_y = event.y - int(mouse_y_ratio * new_display_height)
        
        # 更新缩放显示
        self.zoom_var.set(f"{int(self.zoom_scale * 100)}%")
        
        if self.zoom_after_id is not None:
            self.root.after_cancel(self.zoom_after_id)
        
        self.zoom_after_id = self.root.after(50, self._perform_zoom_redraw)
    
    def _on_mouse_down(self, event):
        """鼠标按下事件"""
        if self.original_img is None:
            return
        
        self.is_dragging = True
        self.drag_start_x = event.x - self.image_offset_x
        self.drag_start_y = event.y - self.image_offset_y
        self.canvas.get_tk_widget().config(cursor='fleur')
    
    def _on_mouse_drag(self, event):
        """鼠标拖拽事件"""
        if not self.is_dragging or self.original_img is None:
            return
        
        new_offset_x = event.x - self.drag_start_x
        new_offset_y = event.y - self.drag_start_y
        
        self.image_offset_x = new_offset_x
        self.image_offset_y = new_offset_y
        
        self._update_canvas_image()
    
    def _on_mouse_up(self, event):
        """鼠标释放事件"""
        self.is_dragging = False
        self.canvas.get_tk_widget().config(cursor='arrow')
    
    def _perform_zoom_redraw(self):
        """执行缩放重绘（延迟调用）"""
        self.zoom_after_id = None
        self._update_canvas_image(force_redraw=True)
    
    def _update_canvas_image(self, force_redraw=False):
        """更新画布上的图片显示"""
        from PIL import Image, ImageTk
        
        if self.original_img is None:
            return
        
        tk_canvas = self.canvas.get_tk_widget()
        
        img_width, img_height = self.original_img.size
        display_width = int(img_width * self.zoom_scale)
        display_height = int(img_height * self.zoom_scale)
        
        if force_redraw or \
           self.current_tk_image is None or \
           self.current_resized_img is None or \
           self.current_resized_img.size != (display_width, display_height):
            
            if self.current_resized_img is not None:
                self.current_resized_img.close()
            resized_img = self.original_img.resize((display_width, display_height), Image.NEAREST)
            self.current_resized_img = resized_img
            self.current_tk_image = ImageTk.PhotoImage(resized_img)
            
            if self.image_item_id is not None:
                tk_canvas.delete(self.image_item_id)
            
            self.image_item_id = tk_canvas.create_image(
                self.image_offset_x, 
                self.image_offset_y, 
                anchor='nw', 
                image=self.current_tk_image
            )
        else:
            tk_canvas.coords(self.image_item_id, self.image_offset_x, self.image_offset_y)
        
    def _clear_image(self):
        """清空图片"""
        self._active_task_id = None
        self.ax.clear()
        self.ax.set_axis_off()
        self.canvas.draw()
        self.current_image_path = None
        self.current_data = None
        self.current_extent = None
        if self.original_img is not None:
            self.original_img.close()
        if self.current_resized_img is not None:
            self.current_resized_img.close()
        self.original_img = None
        self.current_resized_img = None
        self.current_tk_image = None
        self.image_item_id = None
        self.zoom_scale = 1.0
        self.image_offset_x = 0
        self.image_offset_y = 0
        self.is_dragging = False
        if self.zoom_after_id is not None:
            self.root.after_cancel(self.zoom_after_id)
            self.zoom_after_id = None
        self.save_btn.config(state=tk.DISABLED)
        self.draw_btn.config(state=tk.NORMAL)
        self.download_progress.config(maximum=1, value=0)
        # 先取消尚未触发的状态色复原回调，否则它会在稍后把 progress_label
        # 的 fg 改回 Ready 色，覆盖掉本次 _show_status_feedback 设的颜色。
        pending_id = getattr(self, '_status_feedback_after_id', None)
        if pending_id is not None:
            self.root.after_cancel(pending_id)
            self._status_feedback_after_id = None
        self._show_status_feedback('Ready', "就绪")
        self.progress_var.set("就绪")
        self.status_var.set("●  就绪")
        self.zoom_var.set("100%")
        
    def _save_image(self):
        """保存图片"""
        if not self.current_image_path:
            return
        
        original_name = os.path.basename(self.current_image_path)
        
        save_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG图片", "*.png"), ("所有文件", "*.*")],
            initialfile=original_name,
            title="保存图片"
        )
        
        if save_path:
            try:
                import shutil
                shutil.copy2(self.current_image_path, save_path)
                messagebox.showinfo("成功", f"图片已保存到:\n{save_path}")
            except Exception as e:
                self._show_error_dialog("保存失败", f"保存失败: {str(e)}\n\n{traceback.format_exc()}")


def main():
    root = tk.Tk()
    app = HimawariGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()

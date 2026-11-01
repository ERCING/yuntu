"""
Himawari-9 / GOES 卫星云图分析工具 GUI
深色科技主题 · 左侧控制面板 + 右侧云图显示
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


def _platform_identifier(display):
    return 'GOES-17' if display == 'GOES-17（历史）' else display


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
        
        # 初始化UI
        self._setup_styles()
        self._init_ui()
        self._process_ui_queue()
        
    def _setup_styles(self):
        """配置浅色专业主题样式"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        # 浅色专业主题配色：统一取自模块级调色板常量
        # 根窗口背景
        self.root.configure(bg=BG_WINDOW)

        # Frame 样式
        style.configure('Dark.TFrame', background=BG_WINDOW)
        style.configure('Panel.TFrame', background=BG_PANEL)
        style.configure('Card.TFrame', background=BG_SURFACE)
        
        # 标题栏
        style.configure('TitleBar.TFrame', background=BG_PANEL)
        style.configure('Title.TLabel',
                        background=BG_PANEL,
                        foreground='#111827',
                        font=('Segoe UI', 13, 'bold'))
        style.configure('Subtitle.TLabel',
                        background=BG_PANEL,
                        foreground=TEXT_MUTED,
                        font=('Segoe UI', 10))
        style.configure('Version.TLabel',
                        background=BG_HOVER,
                        foreground=TEXT_SUBTLE,
                        font=('Segoe UI', 9),
                        padding=(8, 3))
        
        # 侧边栏分区标题
        style.configure('Section.TLabel',
                        background=BG_PANEL,
                        foreground=TEXT_MUTED,
                        font=('Segoe UI', 10, 'bold'))
        style.configure('SectionDivider.TSeparator',
                        background=BORDER)
        
        # 表单标签
        style.configure('Field.TLabel',
                        background=BG_PANEL,
                        foreground=TEXT_SECONDARY,
                        font=('Segoe UI', 10))
        
        # 下拉框样式
        style.configure('Dark.TCombobox',
                        fieldbackground=BG_INPUT,
                        background=BG_INPUT,
                        foreground=TEXT_PRIMARY,
                        selectbackground=PRIMARY,
                        selectforeground=PRIMARY_FG,
                        bordercolor=BORDER_STRONG,
                        lightcolor=BORDER_STRONG,
                        darkcolor=BORDER_STRONG,
                        arrowcolor=TEXT_MUTED,
                        padding=(8, 5),
                        font=('Segoe UI', 10))
        style.map('Dark.TCombobox',
                  fieldbackground=[('readonly', BG_INPUT), ('focus', BG_PANEL)],
                  background=[('active', BG_HOVER), ('!active', BG_INPUT)],
                  bordercolor=[('focus', BORDER_FOCUS), ('!focus', BORDER_STRONG)],
                  arrowcolor=[('active', TEXT_PRIMARY), ('!active', TEXT_MUTED)])
        
        # 按钮样式 - 主按钮
        style.configure('Primary.TButton',
                        background=PRIMARY,
                        foreground=PRIMARY_FG,
                        borderwidth=0,
                        focusthickness=0,
                        focuscolor='none',
                        font=('Segoe UI', 10, 'bold'),
                        padding=(16, 9),
                        relief='flat')
        style.map('Primary.TButton',
                  background=[('active', PRIMARY_PRESSED),
                              ('!active', PRIMARY),
                              ('disabled', BG_HOVER)],
                  foreground=[('disabled', TEXT_SUBTLE),
                              ('!disabled', PRIMARY_FG)],
                  relief=[('pressed', 'flat'), ('!pressed', 'flat')])
        
        # 按钮样式 - 次按钮
        style.configure('Secondary.TButton',
                        background=BG_PANEL,
                        foreground=TEXT_SECONDARY,
                        bordercolor=BORDER_STRONG,
                        borderwidth=1,
                        focusthickness=0,
                        focuscolor='none',
                        font=('Segoe UI', 10),
                        padding=(14, 8),
                        relief='solid')
        style.map('Secondary.TButton',
                  background=[('active', BG_INPUT),
                              ('!active', BG_PANEL),
                              ('disabled', BG_HOVER)],
                  foreground=[('disabled', TEXT_SUBTLE),
                              ('!disabled', TEXT_SECONDARY)],
                  bordercolor=[('focus', PRIMARY),
                               ('active', '#9ca3af'),
                               ('!active', BORDER_STRONG)])
        
        # 按钮样式 - 危险按钮
        style.configure('Danger.TButton',
                        background=BG_PANEL,
                        foreground=ERROR,
                        bordercolor=ERROR_BORDER,
                        borderwidth=1,
                        focusthickness=0,
                        focuscolor='none',
                        font=('Segoe UI', 10),
                        padding=(14, 8),
                        relief='solid')
        style.map('Danger.TButton',
                  background=[('active', ERROR_BG),
                              ('!active', BG_PANEL),
                              ('disabled', BG_HOVER)],
                  foreground=[('disabled', TEXT_SUBTLE),
                              ('!disabled', ERROR)],
                  bordercolor=[('active', '#fca5a5'),
                               ('!active', ERROR_BORDER)])
        
        # 进度条
        style.configure('Dark.Horizontal.TProgressbar',
                        troughcolor=BORDER,
                        background=PRIMARY,
                        bordercolor=BORDER,
                        lightcolor=PRIMARY,
                        darkcolor=PRIMARY,
                        troughrelief='flat',
                        relief='flat',
                        thickness=6)
        
        # 状态标签
        style.configure('Status.TLabel',
                        background=BG_SURFACE,
                        foreground=TEXT_MUTED,
                        font=('Segoe UI', 10, 'italic'))
        style.configure('Status.Working.TLabel',
                        background=BG_SURFACE,
                        foreground=PRIMARY,
                        font=('Segoe UI', 10))
        style.configure('Status.Success.TLabel',
                        background=BG_SURFACE,
                        foreground=SUCCESS,
                        font=('Segoe UI', 10))
        style.configure('Status.Error.TLabel',
                        background=BG_SURFACE,
                        foreground=ERROR,
                        font=('Segoe UI', 10))
        style.configure('Status.Ready.TLabel',
                        background=BG_SURFACE,
                        foreground=TEXT_MUTED,
                        font=('Segoe UI', 10))
        
        # Labelframe 卡片样式
        style.configure('Card.TLabelframe',
                        background=BG_PANEL,
                        bordercolor=BORDER,
                        borderwidth=1,
                        relief='solid')
        style.configure('Card.TLabelframe.Label',
                        background=BG_PANEL,
                        foreground=TEXT_PRIMARY,
                        font=('Segoe UI', 11, 'bold'))
        
        # 状态栏
        style.configure('StatusBar.TFrame', background=BG_PANEL)
        style.configure('StatusBar.TLabel',
                        background=BG_PANEL,
                        foreground=TEXT_SUBTLE,
                        font=('Segoe UI', 9))
        
        # 进度容器
        style.configure('ProgressCard.TFrame',
                        background=BG_SURFACE,
                        bordercolor=BORDER,
                        relief='solid')
        
        # 工具按钮（小图标按钮）
        style.configure('Tool.TButton',
                        background='transparent',
                        foreground=TEXT_MUTED,
                        borderwidth=0,
                        focusthickness=0,
                        focuscolor='none',
                        font=('Segoe UI', 9),
                        padding=(6, 4),
                        relief='flat')

    def _init_ui(self):
        """初始化 UI - 左侧控制面板 + 右侧云图显示"""
        # 主容器
        main_frame = ttk.Frame(self.root, style='Dark.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === 顶部标题栏 ===
        self._create_title_bar(main_frame)
        
        # === 主内容区（左右布局）===
        content_frame = ttk.Frame(main_frame, style='Dark.TFrame')
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧控制面板
        self._create_sidebar(content_frame)
        
        # 右侧图像显示区
        self._create_image_view(content_frame)
        
        # === 底部状态栏 ===
        self._create_status_bar(main_frame)

    def _create_title_bar(self, parent):
        """创建顶部标题栏"""
        title_bar = tk.Frame(parent, bg='#ffffff', height=48)
        title_bar.pack(fill=tk.X, side=tk.TOP)
        title_bar.pack_propagate(False)
        
        # 左侧标题
        left_frame = tk.Frame(title_bar, bg=BG_PANEL)
        left_frame.pack(side=tk.LEFT, padx=16, pady=8)
        
        # 图标框
        icon_frame = tk.Frame(left_frame, bg=PRIMARY, width=28, height=28)
        icon_frame.pack(side=tk.LEFT, padx=(0, 10))
        icon_frame.pack_propagate(False)
        # 简单的卫星图标（文字代替）
        icon_label = tk.Label(icon_frame, text="◎", bg=PRIMARY, fg=PRIMARY_FG,
                              font=('Segoe UI', 14, 'bold'))
        icon_label.pack(expand=True)
        
        title_text_frame = tk.Frame(left_frame, bg=BG_PANEL)
        title_text_frame.pack(side=tk.LEFT)
        
        title_label = tk.Label(title_text_frame, text="Satellite IR Toolkit",
                               bg=BG_PANEL, fg=TEXT_PRIMARY,
                               font=('Segoe UI', 13, 'bold'))
        title_label.pack(anchor=tk.W)
        
        subtitle_label = tk.Label(title_text_frame, text="Himawari · GOES 云图分析",
                                  bg=BG_PANEL, fg=TEXT_MUTED,
                                  font=('Segoe UI', 9))
        subtitle_label.pack(anchor=tk.W)
        
        # 右侧状态和版本
        right_frame = tk.Frame(title_bar, bg=BG_PANEL)
        right_frame.pack(side=tk.RIGHT, padx=16, pady=10)
        
        # 状态指示器
        status_frame = tk.Frame(right_frame, bg=SUCCESS_BG)
        status_frame.pack(side=tk.RIGHT, padx=(0, 12))
        
        status_dot = tk.Label(status_frame, text="●", bg=SUCCESS_BG, fg=SUCCESS,
                              font=('Segoe UI', 8))
        status_dot.pack(side=tk.LEFT, padx=(8, 4), pady=4)
        
        status_text = tk.Label(status_frame, text="数据就绪",
                               bg=SUCCESS_BG, fg=SUCCESS,
                               font=('Segoe UI', 9))
        status_text.pack(side=tk.LEFT, padx=(0, 8), pady=4)
        
        # 版本号
        version_label = tk.Label(right_frame, text="v1.2.0",
                                 bg=BG_HOVER, fg=TEXT_SUBTLE,
                                 font=('Segoe UI', 9),
                                 padx=8, pady=3)
        version_label.pack(side=tk.RIGHT)

    def _create_sidebar(self, parent):
        """创建左侧控制面板"""
        sidebar = tk.Frame(parent, bg=BG_PANEL, width=320)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        
        # 右侧分隔线
        tk.Frame(sidebar, bg=BORDER, width=1).pack(side=tk.RIGHT, fill=tk.Y)
        
        # 可滚动内容区
        canvas = tk.Canvas(sidebar, bg=BG_PANEL, highlightthickness=0, width=319)
        scrollbar = ttk.Scrollbar(sidebar, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=BG_PANEL)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 0))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 鼠标滚轮支持：仅在指针位于侧边栏内时生效，
        # 避免抢占右侧云图画布的 <MouseWheel> 缩放事件。
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        
        # 内容内边距
        inner_frame = tk.Frame(scrollable_frame, bg=BG_PANEL)
        inner_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        
        # === 时间与卫星 ===
        self._create_section_header(inner_frame, "⏱  时间与卫星")
        
        # 日期时间标签
        tk.Label(inner_frame, text="日期时间 (UTC)",
                 bg=BG_PANEL, fg=TEXT_MUTED,
                 font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(8, 6))
        
        # 年月日行
        date_frame = tk.Frame(inner_frame, bg=BG_PANEL)
        date_frame.pack(fill=tk.X)
        
        # 年
        year_frame = tk.Frame(date_frame, bg=BG_PANEL)
        year_frame.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        self.year_var = tk.StringVar()
        # utcnow() 自 Python 3.12 起弃用且返回 naive datetime，
        # 改用带 tzinfo 的 now(timezone.utc)，避免与后续 UTC 时间换算混淆。
        today = datetime.datetime.now(datetime.timezone.utc)
        year_list = [str(y) for y in range(2015, today.year + 1)]
        self.year_combo = ttk.Combobox(year_frame, textvariable=self.year_var,
                                        values=year_list,
                                        state='readonly', style='Dark.TCombobox')
        self.year_combo.pack(fill=tk.X)
        self.year_var.set(str(today.year))
        self.year_combo.bind('<<ComboboxSelected>>', self._update_days)
        
        # 月
        month_frame = tk.Frame(date_frame, bg=BG_PANEL)
        month_frame.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
        self.month_var = tk.StringVar()
        month_list = [f"{m:02d}" for m in range(1, 13)]
        self.month_combo = ttk.Combobox(month_frame, textvariable=self.month_var,
                                         values=month_list,
                                         state='readonly', style='Dark.TCombobox')
        self.month_combo.pack(fill=tk.X)
        self.month_var.set(f"{today.month:02d}")
        self.month_combo.bind('<<ComboboxSelected>>', self._update_days)
        
        # 日
        day_frame = tk.Frame(date_frame, bg=BG_PANEL)
        day_frame.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))
        self.day_var = tk.StringVar()
        self.day_combo = ttk.Combobox(day_frame, textvariable=self.day_var,
                                       state='readonly', style='Dark.TCombobox')
        self.day_combo.pack(fill=tk.X)
        self._update_days()
        
        # 时间选择
        tk.Label(inner_frame, text="时次",
                 bg=BG_PANEL, fg=TEXT_MUTED,
                 font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(12, 6))
        
        self.time_var = tk.StringVar()
        time_list = [f"{h:02d}:00:00" for h in range(24)]
        self.time_combo = ttk.Combobox(inner_frame, textvariable=self.time_var,
                                        values=time_list,
                                        state='readonly', style='Dark.TCombobox')
        self.time_combo.pack(fill=tk.X)
        self.time_var.set("09:00:00")
        
        # 卫星选择
        tk.Label(inner_frame, text="卫星平台",
                 bg=BG_PANEL, fg=TEXT_MUTED,
                 font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(12, 6))
        
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
        tk.Label(inner_frame, text="观测区域",
                 bg=BG_PANEL, fg=TEXT_MUTED,
                 font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(12, 6))
        
        self.region_var = tk.StringVar(value='F')
        self.region_combo = ttk.Combobox(inner_frame, textvariable=self.region_var,
                                         state='readonly', style='Dark.TCombobox')
        self.region_combo.pack(fill=tk.X)
        self.region_combo['values'] = ('F (全圆盘)', 'T (目标区域/机动观测)')
        self.region_var.set('F (全圆盘)')
        
        # === 数据与显示 ===
        self._create_section_header(inner_frame, "🖥  数据与显示", margin_top=20)
        
        # 数据类型
        tk.Label(inner_frame, text="数据类型",
                 bg=BG_PANEL, fg=TEXT_MUTED,
                 font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(8, 6))
        
        self.data_type_var = tk.StringVar(value='IR')
        type_display = [f"{k} ({v['name']})" for k, v in DATA_TYPES.items()]
        type_combo = ttk.Combobox(inner_frame, textvariable=self.data_type_var,
                                   values=type_display,
                                   style='Dark.TCombobox')
        type_combo.pack(fill=tk.X)
        type_combo.bind('<<ComboboxSelected>>', self._on_type_change)
        type_combo.set('IR (红外窗区)')
        
        # 波段
        tk.Label(inner_frame, text="波段",
                 bg=BG_PANEL, fg=TEXT_MUTED,
                 font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(12, 6))
        
        self.band_var = tk.StringVar()
        self.band_combo = ttk.Combobox(inner_frame, textvariable=self.band_var,
                                         values=DATA_TYPES['IR']['bands'],
                                         style='Dark.TCombobox')
        self.band_combo.pack(fill=tk.X)
        self.band_var.set(DATA_TYPES['IR']['default_band'])
        
        # 色阶方案
        tk.Label(inner_frame, text="色阶方案",
                 bg=BG_PANEL, fg=TEXT_MUTED,
                 font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(12, 6))
        
        self.scheme_var = tk.StringVar()
        self.scheme_combo = ttk.Combobox(inner_frame, textvariable=self.scheme_var,
                                          values=DATA_TYPES['IR']['schemes'],
                                          style='Dark.TCombobox')
        self.scheme_combo.pack(fill=tk.X)
        self.scheme_var.set(DATA_TYPES['IR']['default_scheme'])
        
        # === 操作按钮 ===
        self._create_section_header(inner_frame, "▶  操作", margin_top=20)
        
        # 主操作按钮
        btn_container = tk.Frame(inner_frame, bg=BG_PANEL)
        btn_container.pack(fill=tk.X, pady=(8, 0))
        
        self.draw_btn = ttk.Button(btn_container, text="  绘制云图", command=self._draw_image,
                                   style='Primary.TButton')
        self.draw_btn.pack(fill=tk.X, pady=(0, 8))
        
        # 次要按钮行
        secondary_btn_frame = tk.Frame(inner_frame, bg=BG_PANEL)
        secondary_btn_frame.pack(fill=tk.X)
        
        self.save_btn = ttk.Button(secondary_btn_frame, text="保存图片", command=self._save_image,
                                   state=tk.DISABLED, style='Secondary.TButton')
        self.save_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))
        
        self.clear_btn = ttk.Button(secondary_btn_frame, text="清空", command=self._clear_image,
                                    style='Danger.TButton')
        self.clear_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6, 0))
        
        # === 进度状态 ===
        self._create_section_header(inner_frame, "📊  状态", margin_top=20)
        
        progress_card = tk.Frame(inner_frame, bg=BG_SURFACE,
                                 highlightbackground=BORDER,
                                 highlightthickness=1)
        progress_card.pack(fill=tk.X, pady=(8, 0))
        
        self.progress_var = tk.StringVar(value="就绪")
        self.progress_label = tk.Label(progress_card, textvariable=self.progress_var,
                                       bg=BG_SURFACE, fg=TEXT_SUBTLE,
                                       font=('Segoe UI', 10, 'italic'),
                                       anchor=tk.W, padx=12, pady=8)
        self.progress_label.pack(fill=tk.X)
        
        self.download_progress = ttk.Progressbar(progress_card, mode='determinate',
                                                  maximum=1, value=0,
                                                  style='Dark.Horizontal.TProgressbar')
        self.download_progress.pack(fill=tk.X, padx=12, pady=(0, 12))

    def _create_section_header(self, parent, text, margin_top=0):
        """创建分区标题（带下划线）"""
        frame = tk.Frame(parent, bg=BG_PANEL)
        frame.pack(fill=tk.X, pady=(margin_top, 0))
        
        label = tk.Label(frame, text=text,
                         bg=BG_PANEL, fg=TEXT_MUTED,
                         font=('Segoe UI', 10, 'bold'))
        label.pack(anchor=tk.W)
        
        # 下划线：必须挂在 frame 内部，否则会被 pack 到 parent 的最末尾，
        # 导致下划线出现在所有同级控件之后而非紧贴标题下方。
        line = tk.Frame(frame, bg=BG_HOVER, height=1)
        line.pack(fill=tk.X, pady=(8, 0))

    def _create_image_view(self, parent):
        """创建右侧图像显示区域"""
        view_frame = tk.Frame(parent, bg=BG_WINDOW)
        view_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 工具栏
        toolbar = tk.Frame(view_frame, bg=BG_PANEL, height=40)
        toolbar.pack(fill=tk.X, side=tk.TOP)
        toolbar.pack_propagate(False)
        
        # 工具栏底部分隔线
        tk.Frame(toolbar, bg=BORDER, height=1).pack(side=tk.BOTTOM, fill=tk.X)
        
        # 左侧工具
        toolbar_left = tk.Frame(toolbar, bg=BG_PANEL)
        toolbar_left.pack(side=tk.LEFT, padx=10)
        
        # 缩放显示
        self.zoom_var = tk.StringVar(value="100%")
        zoom_label = tk.Label(toolbar_left, textvariable=self.zoom_var,
                              bg=BG_HOVER, fg=TEXT_MUTED,
                              font=('Segoe UI', 9),
                              padx=10, pady=3)
        zoom_label.pack(side=tk.LEFT, padx=(0, 8))
        
        # 右侧工具（占位）
        toolbar_right = tk.Frame(toolbar, bg=BG_PANEL)
        toolbar_right.pack(side=tk.RIGHT, padx=10)
        
        # 提示文字
        tip_label = tk.Label(toolbar_right, text="滚轮缩放 · 拖拽平移",
                             bg=BG_PANEL, fg=TEXT_SUBTLE,
                             font=('Segoe UI', 9))
        tip_label.pack(side=tk.RIGHT)
        
        # 图像画布容器（深色，与云图黑底融为一体，避免四周出现浅色边框）
        canvas_container = tk.Frame(view_frame, bg='#f0f2f5')
        canvas_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建 matplotlib 画布
        self.fig, self.ax = plt.subplots(figsize=(8, 6), dpi=100)
        self.fig.patch.set_facecolor('#070a0e')
        self.ax.set_axis_off()
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self.canvas = FigureCanvasTkAgg(self.fig, master=canvas_container)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

    def _create_status_bar(self, parent):
        """创建底部状态栏"""
        status_bar = tk.Frame(parent, bg=BG_PANEL, height=26)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_bar.pack_propagate(False)
        
        # 顶部分隔线
        tk.Frame(status_bar, bg=BORDER, height=1).pack(side=tk.TOP, fill=tk.X)
        
        # 左侧状态
        left_frame = tk.Frame(status_bar, bg=BG_PANEL)
        left_frame.pack(side=tk.LEFT, padx=16)
        
        self.status_var = tk.StringVar(value="●  就绪")
        tk.Label(left_frame, textvariable=self.status_var,
                 bg=BG_PANEL, fg=TEXT_SUBTLE,
                 font=('Segoe UI', 9)).pack(side=tk.LEFT)
        
        # 右侧信息
        right_frame = tk.Frame(status_bar, bg=BG_PANEL)
        right_frame.pack(side=tk.RIGHT, padx=16)
        
        tk.Label(right_frame, text="S3 数据源",
                 bg=BG_PANEL, fg=TEXT_SUBTLE,
                 font=('Segoe UI', 9)).pack(side=tk.RIGHT)

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
        """在主线程中依次执行后台线程投递的 UI 更新。"""
        while not self.ui_queue.empty():
            callback, args, kwargs = self.ui_queue.get_nowait()
            callback(*args, **kwargs)
        self.root.after(50, self._process_ui_queue)

    def _set_progress_text(self, text):
        self.progress_var.set(text)

    def _show_status_feedback(self, kind, message, duration=900):
        try:
            after_id = getattr(self, '_status_feedback_after_id', None)
            if after_id is not None:
                self.root.after_cancel(after_id)
            self.progress_var.set(message)
            self.progress_label.configure(fg=self._get_status_color(kind))
            self._status_feedback_after_id = self.root.after(
                duration,
                lambda: self.progress_label.configure(fg=self._get_status_color('Ready')),
            )
        except tk.TclError:
            pass

    def _get_status_color(self, kind):
        """状态文字配色，与 _setup_styles 的浅色调色板保持一致。"""
        colors = {
            'Working': PRIMARY,
            'Success': SUCCESS,
            'Error': ERROR,
            'Ready': TEXT_SUBTLE,
        }
        return colors.get(kind, TEXT_SUBTLE)

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
        dialog.geometry("800x560")
        dialog.minsize(520, 320)
        dialog.configure(bg=BG_PANEL)
        dialog.transient(self.root)

        frame = tk.Frame(dialog, bg=BG_PANEL, padx=16, pady=16)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text=title, bg=BG_PANEL, fg=TEXT_PRIMARY,
                 font=('Segoe UI', 14, 'bold')).pack(anchor=tk.W, pady=(0, 12))

        text_frame = tk.Frame(frame, bg=BG_PANEL)
        text_frame.pack(fill=tk.BOTH, expand=True)
        detail = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 10), undo=False,
                         bg=BG_SURFACE, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY,
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
        buttons = tk.Frame(frame, bg=BG_PANEL)
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

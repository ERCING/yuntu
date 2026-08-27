"""
Himawari-9 卫星云图绘制工具 GUI
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
import json
import urllib.request
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from draw_ir_fulldisk import draw_ir_fulldisk, DATA_TYPES
from satellite_providers import get_archive_window, get_provider_config
from mycolor import color_map


PLATFORM_OPTIONS = ('Himawari-9', 'GOES-16', 'GOES-17（历史）', 'GOES-18', 'GOES-19')


def _platform_identifier(display):
    return 'GOES-17' if display == 'GOES-17（历史）' else display


def _debug_report(hypothesis_id, location, msg, data=None, run_id="pre-fix"):
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.dbg', 'goes-trial.env')
    url = 'http://127.0.0.1:7777/event'
    session_id = 'goes-trial'
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('DEBUG_SERVER_URL='):
                    url = line.split('=', 1)[1].strip()
                elif line.startswith('DEBUG_SESSION_ID='):
                    session_id = line.split('=', 1)[1].strip()
    except Exception:
        pass
    payload = {
        "sessionId": session_id,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "msg": msg,
        "data": data or {},
    }
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=1,
        ).read()
    except Exception:
        pass


# #region debug-point ttk-button-contrast-reporter
def _report_ttk_button_styles(draw_btn):
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '.dbg',
        'ttk-button-contrast.env',
    )
    url = 'http://127.0.0.1:7777/event'
    session_id = 'ttk-button-contrast'
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('DEBUG_SERVER_URL='):
                    url = line.split('=', 1)[1].strip()
                elif line.startswith('DEBUG_SESSION_ID='):
                    session_id = line.split('=', 1)[1].strip()
    except Exception:
        return
    try:
        if session_id != 'ttk-button-contrast':
            return
        style = ttk.Style()
        state = getattr(draw_btn, 'state', None)
        cget = getattr(draw_btn, 'cget', None)
        data = {
            'theme_use': style.theme_use(),
            'primary_foreground': style.lookup('Primary.TButton', 'foreground'),
            'primary_background': style.lookup('Primary.TButton', 'background'),
            'primary_disabled_foreground': style.lookup(
                'Primary.TButton', 'foreground', ('disabled',)
            ),
            'primary_disabled_background': style.lookup(
                'Primary.TButton', 'background', ('disabled',)
            ),
            'draw_btn_state': state() if callable(state) else None,
            'draw_btn_style': cget('style') if callable(cget) else None,
        }
        payload = {
            'sessionId': session_id,
            'runId': 'pre-fix',
            'hypothesisId': 'ttk-button-contrast',
            'location': 'himawari_gui.py:_init_ui',
            'msg': '[DEBUG] ttk button style snapshot',
            'data': data,
        }
        urllib.request.urlopen(
            urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json'},
            ),
            timeout=1,
        ).read()
    except Exception:
        pass
# #endregion


class HimawariGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Himawari-9 卫星云图绘制工具")
        self.root.geometry("1000x750")
        self.root.minsize(800, 600)
        
        # 当前图片数据
        self.current_image_path = None
        self.current_data = None  # 数据数组
        self.current_extent = None  # 图像范围
        
        # matplotlib 相关
        self.fig = None
        self.ax = None
        self.canvas = None
        self.rect_selector = None
        self.cf = None
        
        # 缩放和平移相关
        self.original_img = None  # 原始PIL图像
        self.current_resized_img = None  # 当前缩放后的图片缓存
        self.current_tk_image = None     # 当前Tk图像缓存
        self.zoom_scale = 1.0     # 当前缩放比例
        self.image_offset_x = 0   # 图像显示偏移量
        self.image_offset_y = 0
        self.is_dragging = False  # 是否正在拖拽
        self.drag_start_x = 0     # 拖拽起点
        self.drag_start_y = 0
        self.image_item_id = None # 画布上图片项的ID
        self.zoom_pending = False # 是否有待处理的缩放
        self.zoom_after_id = None # 延迟重绘的after ID
        self.ui_queue = queue.Queue()
        self._next_task_id = 0
        self._active_task_id = None
        
        # 初始化UI
        self._init_ui()
        self._process_ui_queue()
        
    def _init_ui(self):
        # 配置现代深色主题
        self._setup_styles()
        
        # 主框架 - 使用深色背景
        main_frame = ttk.Frame(self.root, style='Dark.TFrame', padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题区域
        title_frame = ttk.Frame(main_frame, style='Dark.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 12))
        
        title_content_frame = ttk.Frame(title_frame, style='Dark.TFrame')
        title_content_frame.pack(side=tk.LEFT)
        title_label = ttk.Label(title_content_frame, text="Himawari / GOES 卫星云图分析工具",
                                style='Title.TLabel', font=('Segoe UI', 16, 'bold'))
        title_label.pack(anchor=tk.W)
        subtitle_label = ttk.Label(title_content_frame, text="UTC 数据选择 · 卫星云图绘制", style='Subtitle.TLabel')
        subtitle_label.pack(anchor=tk.W)

        version_label = ttk.Label(title_frame, text="v1.0", style='Subtitle.TLabel')
        version_label.pack(side=tk.RIGHT)
        
        # 控制面板 - 卡片式设计
        control_frame = ttk.LabelFrame(main_frame, text="参数设置", style='Card.TLabelframe', padding="14")
        control_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(control_frame, text="时间与卫星", style='Section.TLabel').pack(anchor=tk.W, pady=(0, 6))

        # 日期时间选择
        datetime_frame = ttk.Frame(control_frame, style='Dark.TFrame')
        datetime_frame.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(datetime_frame, text="日期时间 (UTC)", style='Label.TLabel').pack(side=tk.LEFT, padx=(0, 12))
        
        # 年份选择 - 从2015年(H8开始)到当前年
        self.year_var = tk.StringVar()
        today = datetime.datetime.utcnow()
        year_list = [str(y) for y in range(2015, today.year + 1)]
        self.year_combo = ttk.Combobox(datetime_frame, textvariable=self.year_var,
                                        values=year_list, width=6, font=('Segoe UI', 11),
                                        state='readonly', style='Modern.TCombobox')
        self.year_combo.pack(side=tk.LEFT, padx=(0, 3))
        self.year_var.set(str(today.year))
        self.year_combo.bind('<<ComboboxSelected>>', self._update_days)
        
        ttk.Label(datetime_frame, text="年", style='SmallLabel.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        
        # 月份选择
        self.month_var = tk.StringVar()
        month_list = [f"{m:02d}" for m in range(1, 13)]
        self.month_combo = ttk.Combobox(datetime_frame, textvariable=self.month_var,
                                         values=month_list, width=4, font=('Segoe UI', 11),
                                         state='readonly', style='Modern.TCombobox')
        self.month_combo.pack(side=tk.LEFT, padx=(0, 3))
        self.month_var.set(f"{today.month:02d}")
        self.month_combo.bind('<<ComboboxSelected>>', self._update_days)
        
        ttk.Label(datetime_frame, text="月", style='SmallLabel.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        
        # 日期选择 - 根据年月动态更新
        self.day_var = tk.StringVar()
        self.day_combo = ttk.Combobox(datetime_frame, textvariable=self.day_var,
                                       width=4, font=('Segoe UI', 11), state='readonly', 
                                       style='Modern.TCombobox')
        self.day_combo.pack(side=tk.LEFT, padx=(0, 5))
        self._update_days()
        
        ttk.Label(datetime_frame, text="日", style='SmallLabel.TLabel').pack(side=tk.LEFT, padx=(0, 8))
        
        # 时间选择 - 下拉滚动选择（精确到小时）
        self.time_var = tk.StringVar()
        time_list = [f"{h:02d}:00:00" for h in range(24)]
        self.time_combo = ttk.Combobox(datetime_frame, textvariable=self.time_var,
                                        values=time_list, width=10, font=('Segoe UI', 11),
                                        state='readonly', style='Modern.TCombobox')
        self.time_combo.pack(side=tk.LEFT)
        self.time_var.set("09:00:00")

        # 卫星选择
        platform_frame = ttk.Frame(control_frame, style='Dark.TFrame')
        platform_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(platform_frame, text="卫星", style='Label.TLabel').pack(side=tk.LEFT, padx=(0, 12))
        self.platform_var = tk.StringVar(value='Himawari-9')
        self.platform_combo = ttk.Combobox(
            platform_frame,
            textvariable=self.platform_var,
            values=PLATFORM_OPTIONS,
            width=18,
            font=('Segoe UI', 11),
            state='readonly',
            style='Modern.TCombobox',
        )
        self.platform_combo.pack(side=tk.LEFT)
        self.platform_combo.bind('<<ComboboxSelected>>', self._on_platform_change)
        
        ttk.Label(control_frame, text="数据与显示", style='Section.TLabel').pack(anchor=tk.W, pady=(0, 6))

        # 数据类型选择
        type_frame = ttk.Frame(control_frame, style='Dark.TFrame')
        type_frame.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(type_frame, text="数据类型", style='Label.TLabel').pack(side=tk.LEFT, padx=(0, 12))
        self.data_type_var = tk.StringVar(value='IR')
        type_display = [f"{k} ({v['name']})" for k, v in DATA_TYPES.items()]
        type_combo = ttk.Combobox(type_frame, textvariable=self.data_type_var, 
                                   values=type_display, width=18, font=('Segoe UI', 11),
                                   style='Modern.TCombobox')
        type_combo.pack(side=tk.LEFT)
        type_combo.bind('<<ComboboxSelected>>', self._on_type_change)
        type_combo.set('IR (红外)')
        
        # 波段选择
        band_frame = ttk.Frame(control_frame, style='Dark.TFrame')
        band_frame.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(band_frame, text="波段", style='Label.TLabel').pack(side=tk.LEFT, padx=(0, 12))
        self.band_var = tk.StringVar()
        self.band_combo = ttk.Combobox(band_frame, textvariable=self.band_var, 
                                         values=DATA_TYPES['IR']['bands'], width=18, 
                                         font=('Segoe UI', 11), style='Modern.TCombobox')
        self.band_combo.pack(side=tk.LEFT)
        self.band_var.set(DATA_TYPES['IR']['default_band'])
        
        # 色阶选择
        scheme_frame = ttk.Frame(control_frame, style='Dark.TFrame')
        scheme_frame.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(scheme_frame, text="色阶方案", style='Label.TLabel').pack(side=tk.LEFT, padx=(0, 12))
        self.scheme_var = tk.StringVar()
        self.scheme_combo = ttk.Combobox(scheme_frame, textvariable=self.scheme_var, 
                                          values=DATA_TYPES['IR']['schemes'], width=18,
                                          font=('Segoe UI', 11), style='Modern.TCombobox')
        self.scheme_combo.pack(side=tk.LEFT)
        self.scheme_var.set(DATA_TYPES['IR']['default_scheme'])
        
        # 区域选择
        region_frame = ttk.Frame(control_frame, style='Dark.TFrame')
        region_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(region_frame, text="观测区域", style='Label.TLabel').pack(side=tk.LEFT, padx=(0, 12))
        self.region_var = tk.StringVar(value='F')
        self.region_combo = ttk.Combobox(region_frame, textvariable=self.region_var,
                                         width=18, font=('Segoe UI', 11), state='readonly', style='Modern.TCombobox')
        self.region_combo.pack(side=tk.LEFT)
        self.region_combo['values'] = ('F (全圆盘)', 'T (目标区域/机动观测)')
        self.region_var.set('F (全圆盘)')
        
        ttk.Label(control_frame, text="绘制与输出", style='Section.TLabel').pack(anchor=tk.W, pady=(0, 6))

        # 操作按钮
        btn_frame = ttk.Frame(control_frame, style='Dark.TFrame')
        btn_frame.pack(fill=tk.X)
        
        self.draw_btn = ttk.Button(btn_frame, text="绘制云图", command=self._draw_image, 
                                  style='Primary.TButton')
        self.draw_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.save_btn = ttk.Button(btn_frame, text="保存图片", command=self._save_image, 
                                   state=tk.DISABLED, style='Secondary.TButton')
        self.save_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.clear_btn = ttk.Button(btn_frame, text="清空", command=self._clear_image, 
                                    style='Danger.TButton')
        self.clear_btn.pack(side=tk.LEFT)

        # #region debug-point ttk-button-contrast-snapshot
        _report_ttk_button_styles(self.draw_btn)
        # #endregion
        
        # 进度标签
        self.progress_var = tk.StringVar(value="就绪")
        self.progress_label = ttk.Label(control_frame, textvariable=self.progress_var, 
                                         style='Progress.TLabel')
        self.progress_label.pack(fill=tk.X, pady=(8, 4))
        self.download_progress = ttk.Progressbar(control_frame, mode='determinate', maximum=1, value=0)
        self.download_progress.pack(fill=tk.X)
        
        # 图片显示区域
        image_frame = ttk.LabelFrame(main_frame, text="云图显示", style='Card.TLabelframe', padding="10")
        image_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建 matplotlib 画布
        self.fig, self.ax = plt.subplots(figsize=(8, 6), dpi=100)
        self.fig.patch.set_facecolor('#ffffff')  # 浅色背景
        self.ax.set_axis_off()
        self.canvas = FigureCanvasTkAgg(self.fig, master=image_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def _setup_styles(self):
        """配置明亮科研主题样式"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        bg_color = '#FFFFFF'
        panel_color = '#F4F7FA'
        card_bg = '#FFFFFF'
        border_color = '#D6E0E8'
        text_color = '#243447'
        muted_color = '#607080'
        primary_color = '#1769AA'
        hover_color = '#145A91'
        danger_bg = '#FDECEC'
        danger_border = '#D77A7A'
        danger_text = '#9B2C2C'

        self.root.configure(bg=bg_color)
        style.configure('Dark.TFrame', background=panel_color)
        style.configure('Card.TLabelframe',
                        background=card_bg,
                        bordercolor=border_color,
                        borderwidth=1,
                        relief='solid')
        style.configure('Card.TLabelframe.Label',
                        background=card_bg,
                        foreground=text_color,
                        font=('Segoe UI', 12, 'bold'))
        style.configure('Title.TLabel',
                        background=panel_color,
                        foreground=text_color,
                        font=('Segoe UI', 16, 'bold'))
        style.configure('Subtitle.TLabel',
                        background=panel_color,
                        foreground=muted_color,
                        font=('Segoe UI', 10))
        style.configure('Section.TLabel',
                        background=card_bg,
                        foreground='#243447',
                        font=('Segoe UI Semibold', 10))
        style.configure('Label.TLabel',
                        background=card_bg,
                        foreground=text_color,
                        font=('Segoe UI', 11))
        style.configure('SmallLabel.TLabel',
                        background=card_bg,
                        foreground=muted_color,
                        font=('Segoe UI', 10))
        style.configure('Progress.TLabel',
                        background=card_bg,
                        foreground=muted_color,
                        font=('Segoe UI', 10, 'italic'))
        style.configure('Working.Progress.TLabel', foreground='#1769AA')
        style.configure('Success.Progress.TLabel', foreground='#2E7D32')
        style.configure('Error.Progress.TLabel', foreground='#B42318')
        style.configure('Ready.Progress.TLabel', foreground='#607080')
        style.configure('Modern.TCombobox',
                        fieldbackground=card_bg,
                        background=panel_color,
                        foreground=text_color,
                        selectbackground=primary_color,
                        selectforeground='white',
                        bordercolor=border_color,
                        borderwidth=1,
                        arrowcolor=text_color)
        style.map('Modern.TCombobox',
                  fieldbackground=[('readonly', card_bg)],
                  background=[('active', panel_color), ('!active', panel_color)],
                  bordercolor=[('focus', primary_color)])
        style.configure('Primary.TButton',
                        background=primary_color,
                        foreground='white',
                        borderwidth=0,
                        focuscolor='none',
                        font=('Segoe UI', 11, 'bold'),
                        padding=(16, 6))
        style.map('Primary.TButton',
                  background=[('active', hover_color), ('!active', primary_color)],
                  foreground=[('disabled', '#607080'), ('!disabled', 'white')],
                  relief=[('pressed', 'flat'), ('!pressed', 'flat')])
        style.configure('Secondary.TButton',
                        background=card_bg,
                        foreground=text_color,
                        bordercolor=border_color,
                        borderwidth=1,
                        focuscolor='none',
                        font=('Segoe UI', 11),
                        padding=(16, 6))
        style.map('Secondary.TButton',
                  background=[('active', panel_color), ('!active', card_bg)],
                  foreground=[('disabled', '#607080'), ('!disabled', '#243447')],
                  bordercolor=[('focus', primary_color)],
                  relief=[('pressed', 'flat'), ('!pressed', 'flat')])
        style.configure('Danger.TButton',
                        background=danger_bg,
                        foreground=danger_text,
                        bordercolor=danger_border,
                        borderwidth=1,
                        focuscolor='none',
                        font=('Segoe UI', 11),
                        padding=(16, 6))
        style.map('Danger.TButton',
                  background=[('active', '#F8DCDC'), ('!active', danger_bg)],
                  foreground=[('disabled', '#607080'), ('!disabled', '#9B2C2C')],
                  bordercolor=[('active', danger_border), ('!active', danger_border)],
                  relief=[('pressed', 'flat'), ('!pressed', 'flat')])
        
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
        self.data_type_var.set('IR (红外)')
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

        if platform in ('GOES-18', 'GOES-19') and int(time_str.split(':')[1]) not in get_provider_config(platform).minutes:
            self._show_error_dialog(
                "日期时间错误",
                "GOES 全圆盘仅提供每 10 分钟一个时次，请选择 00、10、20、30、40 或 50 分钟。",
            )
            return
        
        # #region debug-point time-selection-before-worker
        _debug_report("time-selection-before-worker", "himawari_gui.py:_draw_image", "[DEBUG] before starting draw worker", {
            "time_str": full_time,
            "platform": platform,
        })
        # #endregion
        self._next_task_id += 1
        task_id = self._next_task_id
        self._active_task_id = task_id
        self.draw_btn.config(state=tk.DISABLED)
        self._show_status_feedback('Working', f"正在下载 {DATA_TYPES[data_type]['name']} {band} 数据...")
        self.root.update()
        
        thread = threading.Thread(target=self._draw_worker, 
                                  args=(task_id, full_time, scheme, region, data_type, band, platform))
        thread.daemon = True
        thread.start()
        
    def _draw_worker(self, task_id, time_str, scheme, region, data_type, band, platform='Himawari-9'):
        """后台绘制工作线程"""
        try:
            # #region debug-point A:worker-enter
            _debug_report("A", "himawari_gui.py:_draw_worker", "[DEBUG] worker entered", {
                "time_str": time_str,
                "scheme": scheme,
                "region": region,
                "data_type": data_type,
                "band": band,
                "platform": platform,
                "task_id": task_id,
                "thread_name": threading.current_thread().name,
            })
            # #endregion
            def report_download_progress(downloaded_bytes, total_bytes, file_index, file_count):
                self._enqueue_ui_call(
                    self._set_download_progress,
                    task_id,
                    downloaded_bytes,
                    total_bytes,
                    file_index,
                    file_count,
                )

            # 调用绘制函数，获取路径、数据和范围
            # #region debug-point B:before-render
            _debug_report("B", "himawari_gui.py:_draw_worker", "[DEBUG] invoking draw_ir_fulldisk", {
                "time_str": time_str,
                "scheme": scheme,
                "region": region,
                "data_type": data_type,
                "band": band,
                "platform": platform,
                "task_id": task_id,
            })
            # #endregion
            out_path, data, extent = draw_ir_fulldisk(
                time_str=time_str, scheme=scheme, region=region,
                data_type=data_type, band=band, add_decorations=True,
                progress_callback=report_download_progress, platform=platform,
            )
            # #region debug-point C:render-returned
            _debug_report("C", "himawari_gui.py:_draw_worker", "[DEBUG] draw_ir_fulldisk returned", {
                "out_path": out_path,
                "has_data": data is not None,
                "has_extent": extent is not None,
            })
            # #endregion
            
            # #region debug-point D:schedule-display
            _debug_report("D", "himawari_gui.py:_draw_worker", "[DEBUG] scheduling display on main thread", {
                "current_image_path": out_path,
            })
            # #endregion
            self._enqueue_ui_call(self._on_draw_success, task_id, out_path, data, extent, scheme)
            
        except Exception as e:
            # #region debug-point E:worker-error
            _debug_report("E", "himawari_gui.py:_draw_worker", "[DEBUG] worker raised exception", {
                "error_type": type(e).__name__,
                "error": str(e),
            })
            # #endregion
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
                # 数据不可用的友好提示，区分不同区域
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
            progress_label = getattr(self, 'progress_label', None)
            if after_id is not None:
                self.root.after_cancel(after_id)
            self.progress_var.set(message)
            if progress_label is None:
                return
            progress_label.configure(style=f'{kind}.Progress.TLabel')
            self._status_feedback_after_id = self.root.after(
                duration,
                lambda: progress_label.configure(style='Progress.TLabel'),
            )
        except tk.TclError:
            pass

    def _set_download_progress(self, task_id, downloaded_bytes, total_bytes, file_index, file_count):
        if task_id != self._active_task_id:
            return
        if total_bytes:
            percent = downloaded_bytes / total_bytes * 100
            self.download_progress.config(maximum=total_bytes, value=downloaded_bytes)
            self.progress_var.set(
                f"正在下载：第 {file_index}/{file_count} 个文件，{downloaded_bytes / 1024 / 1024:.1f} / "
                f"{total_bytes / 1024 / 1024:.1f} MB ({percent:.0f}%)"
            )
        else:
            self.download_progress.config(maximum=1, value=0)
            self.progress_var.set(f"正在查询下载文件大小：第 {file_index}/{file_count} 个文件")

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
        self.save_btn.config(state=tk.NORMAL)

    def _show_error_dialog(self, title, message):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("800x560")
        dialog.minsize(520, 320)
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=title, style='Title.TLabel').pack(anchor=tk.W, pady=(0, 8))

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        detail = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 10), undo=False)
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
        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="复制全部", command=copy_all, style='Secondary.TButton').pack(side=tk.LEFT)
        ttk.Button(buttons, text="关闭", command=dialog.destroy, style='Primary.TButton').pack(side=tk.RIGHT)
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        detail.focus_set()

    def _on_draw_error(self, task_id, error_msg):
        if task_id != self._active_task_id:
            return
        self._show_error_dialog("绘制失败", error_msg)
        self._show_status_feedback('Error', "绘制失败")
            
    def _display_image(self, data, scheme):
        """使用PIL直接显示生成的图片文件（保持与命令行一致的布局）"""
        from PIL import Image, ImageTk
        
        # 清除之前的内容
        plt.close(self.fig)
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
        
        # 绑定鼠标事件
        self._bind_mouse_events(tk_canvas)
        
        # 显示图片
        self._update_canvas_image()
    
    def _bind_mouse_events(self, tk_canvas):
        """绑定鼠标事件：滚轮缩放、左键拖拽"""
        # 移除旧绑定
        tk_canvas.unbind('<MouseWheel>')
        tk_canvas.unbind('<ButtonPress-1>')
        tk_canvas.unbind('<B1-Motion>')
        tk_canvas.unbind('<ButtonRelease-1>')
        
        # 绑定新事件
        tk_canvas.bind('<MouseWheel>', self._on_mouse_wheel)
        tk_canvas.bind('<ButtonPress-1>', self._on_mouse_down)
        tk_canvas.bind('<B1-Motion>', self._on_mouse_drag)
        tk_canvas.bind('<ButtonRelease-1>', self._on_mouse_up)
    
    def _on_mouse_wheel(self, event):
        """鼠标滚轮缩放（使用延迟重绘优化性能）"""
        if self.original_img is None:
            return
        
        # 计算缩放方向（Windows滚轮向上为正，向下为负）
        if event.delta > 0:
            zoom_factor = 1.15  # 增大缩放步长
        else:
            zoom_factor = 0.87  # 增大缩放步长
        
        # 限制缩放范围
        new_scale = self.zoom_scale * zoom_factor
        new_scale = max(0.1, min(new_scale, 10.0))  # 限制在0.1x到10x之间
        
        if new_scale == self.zoom_scale:
            return
        
        # 计算缩放前后的图片尺寸
        img_width, img_height = self.original_img.size
        old_display_width = int(img_width * self.zoom_scale)
        old_display_height = int(img_height * self.zoom_scale)
        
        # 计算鼠标位置相对于图片的比例
        mouse_x_ratio = (event.x - self.image_offset_x) / old_display_width if old_display_width > 0 else 0.5
        mouse_y_ratio = (event.y - self.image_offset_y) / old_display_height if old_display_height > 0 else 0.5
        
        # 更新缩放比例和偏移量
        self.zoom_scale = new_scale
        new_display_width = int(img_width * self.zoom_scale)
        new_display_height = int(img_height * self.zoom_scale)
        self.image_offset_x = event.x - int(mouse_x_ratio * new_display_width)
        self.image_offset_y = event.y - int(mouse_y_ratio * new_display_height)
        
        # 使用延迟重绘：取消之前的延迟任务，重新设置新的延迟
        if self.zoom_after_id is not None:
            self.root.after_cancel(self.zoom_after_id)
        
        # 延迟50ms后执行重绘，避免快速滚动时频繁重绘
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
        
        # 计算新的偏移量
        new_offset_x = event.x - self.drag_start_x
        new_offset_y = event.y - self.drag_start_y
        
        # 更新偏移量
        self.image_offset_x = new_offset_x
        self.image_offset_y = new_offset_y
        
        # 更新显示
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
        """更新画布上的图片显示（缩放或平移）
        
        Args:
            force_redraw: 是否强制重新渲染图片（用于缩放后）
        """
        from PIL import Image, ImageTk
        
        if self.original_img is None:
            return
        
        tk_canvas = self.canvas.get_tk_widget()
        
        # 获取原始图片尺寸
        img_width, img_height = self.original_img.size
        
        # 计算当前显示尺寸
        display_width = int(img_width * self.zoom_scale)
        display_height = int(img_height * self.zoom_scale)
        
        # 如果缩放比例变了或强制重绘，需要重新缩放图片
        if force_redraw or \
           self.current_tk_image is None or \
           self.current_resized_img is None or \
           self.current_resized_img.size != (display_width, display_height):
            
            # 使用最快的缩放算法提高性能（牺牲一点画质换取流畅度）
            if self.current_resized_img is not None:
                self.current_resized_img.close()
            resized_img = self.original_img.resize((display_width, display_height), Image.NEAREST)
            self.current_resized_img = resized_img
            self.current_tk_image = ImageTk.PhotoImage(resized_img)
            
            # 如果已有图片项，删除后重新创建
            if self.image_item_id is not None:
                tk_canvas.delete(self.image_item_id)
            
            self.image_item_id = tk_canvas.create_image(
                self.image_offset_x, 
                self.image_offset_y, 
                anchor='nw', 
                image=self.current_tk_image
            )
        else:
            # 只是平移，直接移动已有的图片项
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
        self.zoom_pending = False
        if self.zoom_after_id is not None:
            self.root.after_cancel(self.zoom_after_id)
            self.zoom_after_id = None
        self.save_btn.config(state=tk.DISABLED)
        self.draw_btn.config(state=tk.NORMAL)
        self.download_progress.config(maximum=1, value=0)
        self._show_status_feedback('Ready', "就绪")
        self.progress_var.set("就绪")
        
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

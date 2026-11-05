import inspect
from pathlib import Path
import queue
import unittest
from unittest.mock import patch

from himawari_ir_toolkit.himawari_gui import (
    HimawariGUI,
    PLATFORM_OPTIONS,
    _platform_identifier,
    dark_palette,
    light_palette,
)


class _ForbiddenVar:
    def set(self, _value):
        raise AssertionError("worker thread must not touch Tk variables directly")


class _ForbiddenButton:
    def config(self, **_kwargs):
        raise AssertionError("worker thread must not touch Tk widgets directly")


class _ProgressBar:
    def __init__(self):
        self.maximum = None
        self.value = None

    def config(self, **kwargs):
        self.maximum = kwargs.get("maximum", self.maximum)
        self.value = kwargs.get("value", self.value)


class _TextVar:
    """最小 Tk 变量替身：只记录最后一次 set 的值。"""

    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _FakeLabel:
    """最小 Label 替身：记录 configure 传入的选项。"""

    def __init__(self):
        self.options = {}

    def configure(self, **kwargs):
        self.options.update(kwargs)


def _attach_status_widgets(app):
    """补齐新版 UI 引入的状态栏、缩放标签与进度标签替身。

    这些控件只在主线程的可视化反馈里使用，缺失会让 _show_status_feedback 抛
    AttributeError，从而掩盖真正要验证的状态机行为。
    """
    app.status_var = _TextVar()
    app.zoom_var = _TextVar()
    app.progress_label = _FakeLabel()
    if getattr(app, "root", None) is None:
        app.root = _FakeRoot()
    return app


class _FakeRoot:
    def __init__(self):
        self.after_calls = []
        self.cancelled = []
        self.destroyed = False
        self.quit_called = False

    def after(self, delay, callback, *args):
        self.after_calls.append((delay, callback, args))
        return f"after#{len(self.after_calls)}"

    def after_cancel(self, after_id):
        self.cancelled.append(after_id)

    def quit(self):
        self.quit_called = True

    def destroy(self):
        self.destroyed = True

    def update(self):
        raise AssertionError("worker thread must not call root.update directly")


class TestGUIStyles(unittest.TestCase):
    def test_control_panel_contains_requested_titles_and_existing_actions(self):
        source_path = Path(__file__).resolve().parents[1] / "himawari_gui.py"
        source = source_path.read_text(encoding="utf-8")

        for value in (
            "Satellite IR Toolkit",
            "Himawari · GOES 云图分析",
            "时间与卫星",
            "数据与显示",
            "操作",
            "状态",
            # 日期字段改为内联布局后标签缩短为「日期」，UTC 由字段上下文与
            # 时次下拉共同表达；断言跟着文案更新，但字段本身仍在。
            "日期",
            "时次",
            "卫星平台",
            "观测区域",
            "绘制云图",
            "保存图片",
            # 「清空」按钮已移除：重新绘制会直接覆盖预览，不需要单独的清空入口
        ):
            self.assertIn(value, source)
        self.assertNotIn("clear_btn", source, "清空按钮应已移除")

    def test_sidebar_scrolls_so_all_controls_stay_reachable_at_minimum_size(self):
        """最小窗口下侧边栏内容高于可视区，必须可滚动才能触达全部控件。"""
        source_path = Path(__file__).resolve().parents[1] / "himawari_gui.py"
        source = source_path.read_text(encoding="utf-8")
        sidebar_source = inspect.getsource(HimawariGUI._create_sidebar)

        self.assertIn("1280x800", source)
        self.assertIn("1024, 680", source)
        self.assertIn("tk.Canvas(", sidebar_source)
        self.assertIn("ttk.Scrollbar(", sidebar_source)
        self.assertIn("canvas.configure(yscrollcommand=scrollbar.set)", sidebar_source)
        self.assertIn("self._create_section_header(inner_frame", sidebar_source)

    def test_sidebar_mousewheel_binding_does_not_hijack_image_canvas_zoom(self):
        """侧边栏滚轮滚动必须限定在指针进入侧边栏时，否则会同时触发云图缩放。"""
        sidebar_source = inspect.getsource(HimawariGUI._create_sidebar)

        self.assertIn('canvas.bind("<Enter>"', sidebar_source)
        self.assertIn('canvas.bind("<Leave>"', sidebar_source)
        self.assertIn('canvas.unbind_all("<MouseWheel>")', sidebar_source)
        self.assertNotIn(
            "\n        canvas.bind_all(\"<MouseWheel>\", _on_mousewheel)\n",
            sidebar_source,
        )

    def test_setup_styles_uses_light_professional_palette(self):
        source_path = Path(__file__).resolve().parents[1] / "himawari_gui.py"
        source = source_path.read_text(encoding="utf-8")

        for value in ("#f7f8fa", "#ffffff", "#2563eb", "#1f2937", "#6b7280", "Segoe UI"):
            self.assertIn(value, source)
        for value in (
            "Primary.TButton",
            "Secondary.TButton",
            "Danger.TButton",
            "Dark.TCombobox",
            "Dark.Horizontal.TProgressbar",
        ):
            self.assertIn(value, source)

    def test_setup_styles_selects_clam_theme_for_custom_button_contrast(self):
        source_path = Path(__file__).resolve().parents[1] / "himawari_gui.py"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("style.theme_use('clam')", source)
        self.assertIn("except tk.TclError", source)
        self.assertLess(
            source.index("style.theme_use('clam')"),
            source.index("style.configure('Primary.TButton'"),
        )

    def test_button_styles_define_readable_disabled_foregrounds(self):
        source_path = Path(__file__).resolve().parents[1] / "himawari_gui.py"
        source = source_path.read_text(encoding="utf-8")

        for style_name in ("Primary.TButton", "Secondary.TButton", "Danger.TButton"):
            map_start = source.index(f"style.map('{style_name}'")
            map_end = source.index("style.", map_start + 10)
            style_map = source[map_start:map_end]
            self.assertIn("'disabled'", style_map, f"{style_name} 缺少 disabled 前景色")
            self.assertIn("'!disabled'", style_map, f"{style_name} 缺少启用态前景色")
            self.assertIn("('disabled', p['text_subtle'])", style_map, f"{style_name} disabled 前景色应统一为当前主题的弱化灰")

    def test_status_feedback_defines_four_states_and_uses_each_lifecycle_state(self):
        source_path = Path(__file__).resolve().parents[1] / "himawari_gui.py"
        source = source_path.read_text(encoding="utf-8")
        clear_image_source = inspect.getsource(HimawariGUI._clear_image)
        draw_image_source = inspect.getsource(HimawariGUI._draw_image)
        success_source = inspect.getsource(HimawariGUI._on_draw_success)
        error_source = inspect.getsource(HimawariGUI._on_draw_error)
        feedback_source = inspect.getsource(HimawariGUI._show_status_feedback)
        status_color_source = inspect.getsource(HimawariGUI._get_status_color)

        for kind in ("'Working'", "'Success'", "'Error'", "'Ready'"):
            self.assertIn(kind, status_color_source)

        # 四态配色必须走当前主题的令牌，深色主题下不能再落回浅色常量。
        # 令牌色值断言落在模块级常量定义上，避免函数体直接写裸色值。
        for token, constant, color in (
            ("'primary'", "PRIMARY", "#2563eb"),
            # SUCCESS 由 #059669 调深到 #047857：前者对白底只有 3.77，
            # 低于 WCAG AA 对正文的 4.5 要求，状态栏文字会看不清。
            ("'success'", "SUCCESS", "#047857"),
            ("'error'", "ERROR", "#dc2626"),
            ("'text_subtle'", "TEXT_SUBTLE", "#6b7280"),
        ):
            self.assertIn(token, status_color_source)
            self.assertIn(f"{constant} = '{color}'", source)
        # 函数体内不得出现裸色值：配色必须全部来自令牌表，
        # 否则又会出现「样式表/控件/状态色」三份互相漂移的老问题。
        self.assertNotIn("'#", status_color_source)
        # 不得回退到上一版深色主题的荧光色
        for stale_color in ("#58a6ff", "#3fb950", "#f85149", "#6e7681"):
            self.assertNotIn(stale_color, source)

        # 状态复位必须使用可取消的 after，避免样式永久残留
        self.assertIn("after_cancel", feedback_source)
        self.assertIn("root.after(", feedback_source)

        self.assertIn("_show_status_feedback('Working'", draw_image_source)
        self.assertIn("_show_status_feedback('Success'", success_source)
        self.assertIn("_show_status_feedback('Error'", error_source)
        self.assertIn("_show_status_feedback('Ready'", clear_image_source)
        self.assertNotIn("_show_status_feedback('Success', \"就绪\")", clear_image_source)

        # 任务失效必须发生在视觉反馈之前
        self.assertLess(
            clear_image_source.index("_active_task_id = None"),
            clear_image_source.index("_show_status_feedback"),
        )


class TestGUIThreading(unittest.TestCase):
    def test_draw_worker_queues_ui_work_instead_of_touching_tk(self):
        app = object.__new__(HimawariGUI)
        app.root = _FakeRoot()
        app.progress_var = _ForbiddenVar()
        app.save_btn = _ForbiddenButton()
        app.draw_btn = _ForbiddenButton()
        app.current_image_path = None
        app.current_data = None
        app.current_extent = None
        queued = []
        app._enqueue_ui_call = lambda callback, *args, **kwargs: queued.append((callback, args, kwargs))

        with patch(
            "himawari_ir_toolkit.himawari_gui.draw_ir_fulldisk",
            return_value=("data/example.png", [[1]], (0, 1, 0, 1)),
        ) as draw:
            HimawariGUI._draw_worker(app, 1, "2025-07-24T06:00:00", "IR-CC", "F", "IR", "B14")

        self.assertEqual(draw.call_args.kwargs["platform"], "Himawari-9")
        self.assertEqual(app.current_image_path, None)
        self.assertEqual(len(queued), 2)
        self.assertEqual(queued[0][0], app._on_draw_success)
        self.assertEqual(queued[0][1][0], 1)
        self.assertEqual(queued[1][0], app._set_draw_button_state)
        self.assertEqual(queued[1][1][0], 1)

    def test_process_ui_queue_executes_callbacks(self):
        app = object.__new__(HimawariGUI)
        app.root = _FakeRoot()
        app.ui_queue = queue.Queue()
        received = []

        app.ui_queue.put((received.append, ("ok",), {}))
        HimawariGUI._process_ui_queue(app)

        self.assertEqual(received, ["ok"])
        self.assertEqual(len(app.root.after_calls), 1)

    def test_process_ui_queue_survives_callback_exception_and_reschedules(self):
        """坏回调不能顶掉续排：泵一停，下载进度与失败弹窗会永久静默。"""
        app = object.__new__(HimawariGUI)
        app.root = _FakeRoot()
        app.ui_queue = queue.Queue()
        received = []

        def boom():
            raise RuntimeError("worker callback failed")

        app.ui_queue.put((boom, (), {}))
        app.ui_queue.put((received.append, ("after-boom",), {}))

        with patch("himawari_ir_toolkit.himawari_gui.traceback.print_exc") as log:
            HimawariGUI._process_ui_queue(app)

        # 前一个回调抛异常，后一个仍要执行
        self.assertEqual(received, ["after-boom"])
        # 异常要留痕，但泵必须照常续排
        self.assertTrue(log.called)
        self.assertEqual(len(app.root.after_calls), 1)

    def test_ui_pump_stops_rescheduling_while_closing(self):
        """关窗后泵不得再续排，否则 after 会在窗口销毁后触发并报 bgerror。"""
        app = object.__new__(HimawariGUI)
        app.root = _FakeRoot()
        app.ui_queue = queue.Queue()
        app._closing = True

        HimawariGUI._process_ui_queue(app)

        self.assertEqual(app.root.after_calls, [])
        self.assertIsNone(app._pump_after_id)

    def test_on_close_cancels_pending_callbacks_and_destroys_window(self):
        app = object.__new__(HimawariGUI)
        app.root = _FakeRoot()
        app._draw_in_flight = False
        app._closing = False
        app._pump_after_id = "pump"
        app._resize_after_id = "resize"
        app.zoom_after_id = "zoom"
        app._status_feedback_after_id = "status"

        HimawariGUI._on_close(app)

        self.assertTrue(app.root.destroyed)
        self.assertEqual(
            sorted(app.root.cancelled), ["pump", "resize", "status", "zoom"]
        )
        # 取消后必须置空，避免二次取消已失效的 id
        self.assertIsNone(app._pump_after_id)
        self.assertIsNone(app.zoom_after_id)

    def test_on_close_asks_before_aborting_in_flight_draw(self):
        app = object.__new__(HimawariGUI)
        app.root = _FakeRoot()
        app._draw_in_flight = True
        app._closing = False
        app._pump_after_id = None
        app._resize_after_id = None
        app.zoom_after_id = None
        app._status_feedback_after_id = None

        with patch("himawari_ir_toolkit.himawari_gui.messagebox.askyesno",
                   return_value=False) as ask:
            HimawariGUI._on_close(app)

        # 用户选择"不退出"：窗口必须还在，任务继续
        self.assertTrue(ask.called)
        self.assertFalse(app.root.destroyed)
        self.assertFalse(app._closing)

        with patch("himawari_ir_toolkit.himawari_gui.messagebox.askyesno",
                   return_value=True):
            HimawariGUI._on_close(app)

        self.assertTrue(app.root.destroyed)

    def test_download_progress_shows_speed_and_remaining_time(self):
        """慢网下用户最需要知道"还要多久"，所以状态栏要显示速率与剩余时间。"""
        app = object.__new__(HimawariGUI)
        app.progress_var = type("ProgressText", (), {"value": None, "set": lambda self, value: setattr(self, "value", value)})()
        app.download_progress = _ProgressBar()
        app._active_task_id = 1

        # 第一次采样只建立基线，还不该有速率
        with patch("himawari_ir_toolkit.himawari_gui.time.monotonic", return_value=100.0):
            HimawariGUI._set_download_progress(app, 1, 1 * 1024 * 1024, 10 * 1024 * 1024, 1, 1)
        self.assertNotIn("MB/s", app.progress_var.value)

        # 2 秒后前进 4MB → 2.0 MB/s，剩余 5MB → 约 2s
        with patch("himawari_ir_toolkit.himawari_gui.time.monotonic", return_value=102.0):
            HimawariGUI._set_download_progress(app, 1, 5 * 1024 * 1024, 10 * 1024 * 1024, 1, 1)

        text = app.progress_var.value
        self.assertIn("2.0 MB/s", text)
        self.assertIn("剩余", text)
        self.assertIn("MB", text)

    def test_download_rate_ignores_samples_that_are_too_close(self):
        """同一轮 UI 泵里收到多个块回调时，间隔趋近 0 会让速率爆表，必须跳过。"""
        app = object.__new__(HimawariGUI)
        app._active_task_id = 1
        app.progress_var = type("ProgressText", (), {"value": None, "set": lambda self, value: setattr(self, "value", value)})()
        app.download_progress = _ProgressBar()

        with patch("himawari_ir_toolkit.himawari_gui.time.monotonic", return_value=100.0):
            HimawariGUI._update_download_rate(app, 1024 * 1024)
        # 间隔仅 0.01s：不采样
        with patch("himawari_ir_toolkit.himawari_gui.time.monotonic", return_value=100.01):
            rate = HimawariGUI._update_download_rate(app, 2 * 1024 * 1024)
        self.assertIsNone(rate)

    def test_download_rate_ignores_counter_regression(self):
        """重试会让字节计数回退，此时不得算出负速率。"""
        app = object.__new__(HimawariGUI)
        with patch("himawari_ir_toolkit.himawari_gui.time.monotonic", return_value=100.0):
            HimawariGUI._update_download_rate(app, 8 * 1024 * 1024)
        app._download_rate = 1.5e6
        with patch("himawari_ir_toolkit.himawari_gui.time.monotonic", return_value=102.0):
            rate = HimawariGUI._update_download_rate(app, 2 * 1024 * 1024)
        self.assertEqual(rate, 1.5e6)

    def test_eta_formatting(self):
        app = object.__new__(HimawariGUI)
        self.assertEqual(HimawariGUI._format_eta(app, 0, 1e6), "")
        self.assertEqual(HimawariGUI._format_eta(app, 1024, 0), "")
        self.assertEqual(HimawariGUI._format_eta(app, 2e6, 1e6), " · 剩余 2s")
        self.assertEqual(HimawariGUI._format_eta(app, 90e6, 1e6), " · 剩余 1m30s")
        # 超过 1 小时没有参考意义，不显示
        self.assertEqual(HimawariGUI._format_eta(app, 7200e6, 1e6), "")

    def test_viewport_box_covers_whole_image_when_zoomed_out(self):
        """缩小到整幅可见时，裁剪框应覆盖整张图，输出尺寸等于显示尺寸。"""
        box, out_size, place = HimawariGUI._compute_viewport_box(
            img_w=1000, img_h=800, scale=0.5,
            offset_x=0, offset_y=0, canvas_w=800, canvas_h=600,
        )
        self.assertEqual(box, (0, 0, 1000, 800))
        self.assertEqual(out_size, (500, 400))
        self.assertEqual(place, (0, 0))

    def test_viewport_box_crops_to_visible_area_when_zoomed_in(self):
        """放大后只应处理可见区域——这是丝滑与否的关键。

        实测 5517×5500 原图：整幅缩放 zoom=0.9 要 332ms、zoom=2 要 1011ms；
        只处理可见区稳定在 3~8ms。原生看图器就是这么做的。
        """
        box, out_size, place = HimawariGUI._compute_viewport_box(
            img_w=5517, img_h=5500, scale=4.0,
            offset_x=0, offset_y=0, canvas_w=800, canvas_h=600,
        )
        # 4 倍放大时可见区只有 200×150 个源像素
        self.assertLessEqual(box[2] - box[0], 201)
        self.assertLessEqual(box[3] - box[1], 151)
        # 输出尺寸受画布约束，不会随缩放级别暴涨
        self.assertLessEqual(out_size[0], 800)
        self.assertLessEqual(out_size[1], 600)

    def test_viewport_box_returns_none_when_image_out_of_view(self):
        box, out_size, place = HimawariGUI._compute_viewport_box(
            img_w=1000, img_h=800, scale=1.0,
            offset_x=-5000, offset_y=-5000, canvas_w=800, canvas_h=600,
        )
        self.assertIsNone(box)
        self.assertIsNone(out_size)
        self.assertIsNone(place)

    def test_viewport_box_handles_zero_scale(self):
        self.assertEqual(
            HimawariGUI._compute_viewport_box(1000, 800, 0, 0, 0, 800, 600),
            (None, None, None),
        )

    def test_download_progress_updates_text_and_byte_progress_bar(self):
        app = object.__new__(HimawariGUI)
        app.progress_var = type("ProgressText", (), {"value": None, "set": lambda self, value: setattr(self, "value", value)})()
        app.download_progress = _ProgressBar()
        app._active_task_id = 1

        HimawariGUI._set_download_progress(app, 1, 5 * 1024 * 1024, 10 * 1024 * 1024, 1, 2)

        self.assertEqual(app.download_progress.maximum, 10 * 1024 * 1024)
        self.assertEqual(app.download_progress.value, 5 * 1024 * 1024)
        self.assertIn("50%", app.progress_var.value)
        self.assertIn("5.0 / 10.0 MB", app.progress_var.value)

    def test_draw_error_uses_copyable_error_dialog(self):
        app = object.__new__(HimawariGUI)
        app.progress_var = type("ProgressText", (), {"value": None, "set": lambda self, value: setattr(self, "value", value)})()
        _attach_status_widgets(app)
        shown = []
        app._show_error_dialog = lambda title, message: shown.append((title, message))

        app._active_task_id = 1
        HimawariGUI._on_draw_error(app, 1, "完整错误详情")

        self.assertEqual(shown, [("绘制失败", "完整错误详情")])
        self.assertEqual(app.progress_var.value, "绘制失败")

    def test_expired_callbacks_after_clear_do_not_restore_ui_state(self):
        class _Button:
            def __init__(self):
                self.state = None

            def config(self, **kwargs):
                self.state = kwargs.get("state", self.state)

        app = object.__new__(HimawariGUI)
        app.ax = type("Axis", (), {"clear": lambda self: None, "set_axis_off": lambda self: None})()
        app.canvas = type("Canvas", (), {"draw": lambda self: None})()
        app.root = _FakeRoot()
        app.save_btn = _Button()
        app.draw_btn = _Button()
        app.progress_var = type("ProgressText", (), {"value": None, "set": lambda self, value: setattr(self, "value", value)})()
        app.download_progress = _ProgressBar()
        app.current_image_path = "image.png"
        app.current_data = [[1]]
        app.current_extent = (0, 1, 0, 1)
        app.original_img = None
        app.current_resized_img = None
        app.current_tk_image = None
        app.image_item_id = None
        app.zoom_scale = 1.0
        app.image_offset_x = 0
        app.image_offset_y = 0
        app.is_dragging = False
        app.zoom_pending = False
        app.zoom_after_id = None
        app._active_task_id = 4
        _attach_status_widgets(app)
        app._display_image = lambda *_args: self.fail("expired success must not display an image")
        shown = []
        app._show_error_dialog = lambda *args: shown.append(args)

        HimawariGUI._clear_image(app)
        HimawariGUI._on_draw_success(app, 4, "old.png", [[1]], (0, 1, 0, 1), "IR-CC")
        HimawariGUI._on_draw_error(app, 4, "old error")
        HimawariGUI._set_draw_button_state(app, 4, "normal")

        self.assertIsNone(app.current_image_path)
        self.assertEqual(app.progress_var.value, "就绪")
        self.assertEqual(app.save_btn.state, "disabled")
        self.assertEqual(app.draw_btn.state, "normal")
        self.assertEqual(shown, [])

    def test_clear_image_ignores_old_button_callback_after_restoring_normal_state(self):
        class _Button:
            def __init__(self):
                self.state = None

            def config(self, **kwargs):
                self.state = kwargs.get("state", self.state)

        app = object.__new__(HimawariGUI)
        app.ax = type("Axis", (), {"clear": lambda self: None, "set_axis_off": lambda self: None})()
        app.canvas = type("Canvas", (), {"draw": lambda self: None})()
        app.save_btn = _Button()
        app.draw_btn = _Button()
        app.progress_var = type("ProgressText", (), {"set": lambda self, _value: None})()
        app.download_progress = _ProgressBar()
        app.current_image_path = None
        app.current_data = None
        app.current_extent = None
        app.original_img = None
        app.current_resized_img = None
        app.current_tk_image = None
        app.image_item_id = None
        app.zoom_scale = 1.0
        app.image_offset_x = 0
        app.image_offset_y = 0
        app.is_dragging = False
        app.zoom_pending = False
        app.zoom_after_id = None
        app._active_task_id = 4
        _attach_status_widgets(app)

        HimawariGUI._clear_image(app)
        HimawariGUI._set_draw_button_state(app, 4, "disabled")

        self.assertEqual(app.draw_btn.state, "normal")

    def test_draw_worker_queues_friendly_goes_no_cmipf_error_without_traceback(self):
        app = object.__new__(HimawariGUI)
        queued = []
        app._enqueue_ui_call = lambda callback, *args, **kwargs: queued.append((callback, args, kwargs))

        with patch(
            "himawari_ir_toolkit.himawari_gui.draw_ir_fulldisk",
            side_effect=ValueError("No CMIPF scan available"),
        ):
            HimawariGUI._draw_worker(app, 1, "2025-07-24T06:00:00", "IR-CC", "F", "IR", "B14", "GOES-18")

        error_calls = [call for call in queued if call[0] == app._on_draw_error]
        self.assertEqual(len(error_calls), 1)
        error_message = error_calls[0][1][1]
        self.assertIn("所选 UTC 时次没有可用的 GOES 全圆盘数据。请确认卫星和时间，或选择相邻的 10 分钟时次。", error_message)
        self.assertIn("No CMIPF scan available", error_message)
        self.assertNotIn("Traceback", error_message)

    def test_draw_worker_queues_friendly_h5netcdf_error_without_traceback(self):
        app = object.__new__(HimawariGUI)
        queued = []
        app._enqueue_ui_call = lambda callback, *args, **kwargs: queued.append((callback, args, kwargs))

        with patch(
            "himawari_ir_toolkit.himawari_gui.draw_ir_fulldisk",
            side_effect=ValueError("unrecognized engine 'h5netcdf' must be one of your download engines"),
        ):
            HimawariGUI._draw_worker(app, 1, "2025-07-24T06:00:00", "IR-CC", "F", "IR", "B14", "GOES-18")

        error_calls = [call for call in queued if call[0] == app._on_draw_error]
        self.assertEqual(len(error_calls), 1)
        error_message = error_calls[0][1][1]
        self.assertIn("缺少 GOES NetCDF 读取组件", error_message)
        self.assertIn("h5netcdf", error_message)
        self.assertIn("python -m pip install -r requirements.txt", error_message)
        self.assertIn(".venv\\Scripts\\python.exe himawari_ir_toolkit\\himawari_gui.py", error_message)
        self.assertNotIn("Traceback", error_message)

    def test_start_gui_batch_uses_project_venv_and_gui_path(self):
        batch_path = Path(__file__).resolve().parents[2] / "start_gui.bat"
        batch_text = batch_path.read_text(encoding="ascii")

        self.assertIn(".venv\\Scripts\\python.exe", batch_text)
        self.assertIn("himawari_ir_toolkit\\himawari_gui.py", batch_text)

    def test_draw_worker_queues_friendly_goes_file_not_found_error_without_traceback(self):
        app = object.__new__(HimawariGUI)
        queued = []
        app._enqueue_ui_call = lambda callback, *args, **kwargs: queued.append((callback, args, kwargs))

        with patch(
            "himawari_ir_toolkit.himawari_gui.draw_ir_fulldisk",
            side_effect=FileNotFoundError("noaa-goes19/ABI-L2-CMIPF/2024/214/09/"),
        ):
            HimawariGUI._draw_worker(app, 1, "2024-08-01T09:00:00", "IR-CC", "F", "IR", "B14", "GOES-19")

        error_calls = [call for call in queued if call[0] == app._on_draw_error]
        self.assertEqual(len(error_calls), 1)
        error_message = error_calls[0][1][1]
        self.assertIn("所选 UTC 时次没有可用的 GOES 全圆盘数据", error_message)
        self.assertIn("noaa-goes19/ABI-L2-CMIPF/2024/214/09/", error_message)
        self.assertNotIn("Traceback", error_message)

    def test_clear_image_closes_open_pil_image(self):
        class _Image:
            closed = False

            def close(self):
                self.closed = True

        class _Button:
            def __init__(self):
                self.state = None

            def config(self, **kwargs):
                self.state = kwargs.get("state", self.state)

        app = object.__new__(HimawariGUI)
        app.ax = type("Axis", (), {"clear": lambda self: None, "set_axis_off": lambda self: None})()
        app.canvas = type("Canvas", (), {"draw": lambda self: None})()
        app.save_btn = type("SaveButton", (), {"config": lambda self, **_kwargs: None})()
        app.draw_btn = _Button()
        app.progress_var = type("ProgressText", (), {"set": lambda self, _value: None})()
        app.download_progress = _ProgressBar()
        app.current_image_path = None
        app.current_data = None
        app.current_extent = None
        image = _Image()
        app.original_img = image
        app.current_resized_img = None
        app.current_tk_image = None
        app.image_item_id = None
        app.zoom_scale = 1.0
        app.image_offset_x = 0
        app.image_offset_y = 0
        app.is_dragging = False
        app.zoom_pending = False
        app.zoom_after_id = None
        _attach_status_widgets(app)

        HimawariGUI._clear_image(app)

        self.assertTrue(image.closed)
        self.assertIsNone(app.original_img)
        self.assertEqual(app.draw_btn.state, "normal")

    def test_update_canvas_image_closes_previous_resized_image_before_replacing_it(self):
        class _Image:
            def __init__(self, size):
                self.size = size
                self.closed = False

            def close(self):
                self.closed = True

        class _OriginalImage:
            size = (100, 100)

            def __init__(self, resized_image):
                self.resized_image = resized_image

            def crop(self, _box):
                # 只渲染可见区后，绘制走 crop → resize；替身按需返回同一对象
                return self

            def resize(self, _size, _resample):
                return self.resized_image

        class _Canvas:
            def get_tk_widget(self):
                return self

            def winfo_width(self):
                return 100

            def winfo_height(self):
                return 100

            def create_image(self, *_args, **_kwargs):
                return 1

            def itemconfigure(self, *_args, **_kwargs):
                pass

            def coords(self, *_args, **_kwargs):
                pass

        previous_image = _Image((100, 100))
        app = object.__new__(HimawariGUI)
        app.original_img = _OriginalImage(_Image((100, 100)))
        app.current_resized_img = previous_image
        app.current_tk_image = object()
        app.canvas = _Canvas()
        app.zoom_scale = 1.0
        app.image_offset_x = 0
        app.image_offset_y = 0
        app.image_item_id = None

        with patch("PIL.ImageTk.PhotoImage", return_value=object()):
            HimawariGUI._update_canvas_image(app, force_redraw=True)

        self.assertTrue(previous_image.closed)

    def test_clear_image_resets_download_progress_bar(self):
        class _Button:
            def __init__(self):
                self.state = None

            def config(self, **kwargs):
                self.state = kwargs.get("state", self.state)

        app = object.__new__(HimawariGUI)
        app.ax = type("Axis", (), {"clear": lambda self: None, "set_axis_off": lambda self: None})()
        app.canvas = type("Canvas", (), {"draw": lambda self: None})()
        app.save_btn = type("SaveButton", (), {"config": lambda self, **_kwargs: None})()
        app.draw_btn = _Button()
        app.progress_var = type("ProgressText", (), {"value": None, "set": lambda self, value: setattr(self, "value", value)})()
        app.download_progress = _ProgressBar()
        app.download_progress.config(maximum=100, value=100)
        app.current_image_path = "image.png"
        app.current_data = [[1]]
        app.current_extent = (0, 1, 0, 1)
        app.original_img = None
        app.current_resized_img = None
        app.current_tk_image = None
        app.image_item_id = None
        app.zoom_scale = 1.0
        app.image_offset_x = 0
        app.image_offset_y = 0
        app.is_dragging = False
        app.zoom_pending = False
        app.zoom_after_id = None
        _attach_status_widgets(app)

        HimawariGUI._clear_image(app)

        self.assertEqual(app.download_progress.maximum, 1)
        self.assertEqual(app.download_progress.value, 0)
        self.assertEqual(app.draw_btn.state, "normal")


class TestGUIPlatformSelection(unittest.TestCase):
    class _Var:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class _Combo:
        def __init__(self):
            self.values = ()
            self.state = None

        def __setitem__(self, key, value):
            if key == "values":
                self.values = tuple(value)

        def config(self, **kwargs):
            self.state = kwargs.get("state", self.state)

    class _Button:
        def __init__(self):
            self.state = None

        def config(self, **kwargs):
            self.state = kwargs.get("state", self.state)

    class _Root:
        def __init__(self):
            self.after_calls = []

        def update(self):
            pass

        def after(self, delay, callback, *args):
            self.after_calls.append((delay, callback, args))

        def after_cancel(self, _after_id):
            pass

    def _platform_app(self, platform="Himawari-9", time="09:00:00"):
        app = object.__new__(HimawariGUI)
        app.platform_var = self._Var(platform)
        app.region_var = self._Var("F (全圆盘)")
        app.time_var = self._Var(time)
        app.year_var = self._Var("2024")
        app.month_var = self._Var("08")
        app.day_var = self._Var("01")
        app.region_combo = self._Combo()
        app.day_combo = self._Combo()
        app.time_combo = self._Combo()
        app.data_type_var = self._Var("IR (红外)")
        app.band_var = self._Var()
        app.scheme_var = self._Var()
        app.band_combo = self._Combo()
        app.scheme_combo = self._Combo()
        return app

    def test_platform_values_include_historical_goes_label_and_stable_mapping(self):
        self.assertEqual(
            PLATFORM_OPTIONS,
            ("Himawari-9", "GOES-16", "GOES-17（历史）", "GOES-18", "GOES-19"),
        )
        self.assertEqual(_platform_identifier("GOES-17（历史）"), "GOES-17")
        self.assertEqual(_platform_identifier("GOES-18"), "GOES-18")

    def test_platform_change_clamps_goes_date_to_archive_window(self):
        app = self._platform_app("GOES-17（历史）", "09:20:00")
        app.year_var = self._Var("2018")
        app.month_var = self._Var("12")
        app.day_var = self._Var("03")
        app.day_combo = self._Combo()

        HimawariGUI._on_platform_change(app, None)

        self.assertEqual((app.year_var.get(), app.month_var.get(), app.day_var.get()), ("2018", "12", "04"))
        self.assertEqual(app.time_var.get(), "09:20:00")

    def test_platform_change_clamps_goes_end_date(self):
        app = self._platform_app("GOES-16", "09:20:00")
        app.year_var = self._Var("2025")
        app.month_var = self._Var("05")
        app.day_var = self._Var("01")
        app.day_combo = self._Combo()

        HimawariGUI._on_platform_change(app, None)

        self.assertEqual((app.year_var.get(), app.month_var.get(), app.day_var.get()), ("2025", "04", "06"))
        self.assertEqual(app.time_var.get(), "09:20:00")

    def test_platform_change_clamps_goes17_historical_end_date(self):
        app = self._platform_app("GOES-17（历史）", "09:20:00")

        HimawariGUI._on_platform_change(app, None)

        self.assertEqual((app.year_var.get(), app.month_var.get(), app.day_var.get()), ("2023", "01", "10"))
        self.assertEqual(app.time_var.get(), "09:20:00")

    def test_draw_worker_uses_goes17_stable_identifier(self):
        app = object.__new__(HimawariGUI)
        queued = []
        app._enqueue_ui_call = lambda callback, *args, **kwargs: queued.append((callback, args, kwargs))

        with patch(
            "himawari_ir_toolkit.himawari_gui.draw_ir_fulldisk",
            return_value=("data/example.png", [[1]], (0, 1, 0, 1)),
        ) as draw:
            HimawariGUI._draw_worker(app, 1, "2024-08-01T09:20:00", "IR-CC", "F", "IR", "B14", "GOES-17")

        self.assertEqual(draw.call_args.kwargs["platform"], "GOES-17")

    def test_platform_change_to_goes_offers_all_day_ten_minute_times(self):
        for platform in ("GOES-16", "GOES-17（历史）", "GOES-18", "GOES-19"):
            with self.subTest(platform=platform):
                app = self._platform_app(platform, "09:00:00")

                HimawariGUI._on_platform_change(app, None)

                self.assertEqual(app.region_combo.values, ("F (全圆盘)",))
                self.assertEqual(app.region_var.get(), "F (全圆盘)")
                self.assertEqual(len(app.time_combo.values), 144)
                self.assertEqual(app.time_combo.values[0], "00:00:00")
                self.assertEqual(app.time_combo.values[-1], "23:50:00")
                self.assertIn("09:00:00", app.time_combo.values)
                self.assertIn("10:00:00", app.time_combo.values)
                self.assertIn("23:50:00", app.time_combo.values)
                self.assertEqual(app.time_var.get(), "09:00:00")
                self.assertEqual(app.band_var.get(), "B14")
                self.assertEqual(app.scheme_var.get(), "IR-CC")

    def test_platform_change_to_goes_preserves_valid_ten_minute_time(self):
        app = self._platform_app("GOES-18", "09:20:00")

        HimawariGUI._on_platform_change(app, None)

        self.assertEqual(len(app.time_combo.values), 144)
        self.assertEqual(app.time_combo.values[0], "00:00:00")
        self.assertEqual(app.time_combo.values[-1], "23:50:00")
        self.assertIn("10:00:00", app.time_combo.values)
        self.assertEqual(app.time_var.get(), "09:20:00")

    def test_platform_change_to_goes_normalizes_invalid_minute_to_hour_start(self):
        app = self._platform_app("GOES-18", "09:07:00")

        HimawariGUI._on_platform_change(app, None)

        self.assertEqual(len(app.time_combo.values), 144)
        self.assertEqual(app.time_var.get(), "09:00:00")

    def test_platform_change_back_to_himawari_restores_ten_minute_times(self):
        """Himawari 全圆盘是每 10 分钟一张，不是每小时一张。

        历史错误：ProviderConfig 里曾配成 minutes=(0,)，界面只能选整点，
        用户无法选择 09:20 这类真实存在的时次。
        """
        app = self._platform_app("Himawari-9", "09:30:00")

        HimawariGUI._on_platform_change(app, None)

        self.assertEqual(len(app.time_combo.values), 144)
        self.assertEqual(app.time_combo.values[0], "00:00:00")
        self.assertEqual(app.time_combo.values[-1], "23:50:00")
        self.assertIn("09:20:00", app.time_combo.values)
        # 09:30 本身是合法时次，不该被改成整点
        self.assertEqual(app.time_var.get(), "09:30:00")

    def test_region_combo_is_created_readonly_and_remains_readonly_after_platform_change(self):
        source = inspect.getsource(HimawariGUI._create_sidebar)
        self.assertIn("self.region_combo = ttk.Combobox", source)
        self.assertIn("state='readonly'", source[source.index("self.region_combo = ttk.Combobox"):])

        app = self._platform_app("GOES-18")
        HimawariGUI._on_platform_change(app, None)

        self.assertEqual(app.region_combo.state, "readonly")

    def test_draw_image_starts_worker_with_goes_platform(self):
        app = self._platform_app("GOES-19", "09:20:00")
        app.year_var = self._Var("2025")
        app.month_var = self._Var("07")
        app.day_var = self._Var("24")
        app.root = self._Root()
        app.draw_btn = self._Button()
        app.progress_var = self._Var()
        app.status_var = self._Var()
        app.progress_label = _FakeLabel()
        app._next_task_id = 0
        app._active_task_id = None
        app._show_error_dialog = lambda *_args: self.fail("valid GOES time must not show an error")
        started = []

        class _Thread:
            def __init__(self, target, args):
                started.append((target, args))
                self.daemon = False

            def start(self):
                pass

        with patch("himawari_ir_toolkit.himawari_gui.threading.Thread", _Thread):
            HimawariGUI._draw_image(app)

        self.assertEqual(started[0][0], app._draw_worker)
        args = started[0][1]
        # 参数顺序：(task_id, time, scheme, region, data_type, band, platform,
        # vmin, vmax, reverse_cmap)。按位置断言而不是取 [-1]，
        # 否则以后再加参数这条断言会静默地测错对象。
        self.assertEqual(args[6], "GOES-19")
        # 温度范围默认留空 = 用色阶表自带范围，接上控件不改变既有出图外观
        self.assertIsNone(args[7])
        self.assertIsNone(args[8])
        self.assertFalse(args[9])

    def test_draw_image_rejects_invalid_goes_minute_without_starting_thread(self):
        app = self._platform_app("GOES-19", "09:15:00")
        app.year_var = self._Var("2025")
        app.month_var = self._Var("07")
        app.day_var = self._Var("24")
        app.root = self._Root()
        app.draw_btn = self._Button()
        app.progress_var = self._Var()
        app._next_task_id = 0
        shown = []
        app._show_error_dialog = lambda title, message: shown.append((title, message))

        with patch("himawari_ir_toolkit.himawari_gui.threading.Thread") as thread:
            HimawariGUI._draw_image(app)

        thread.assert_not_called()
        self.assertEqual(
            shown,
            [("日期时间错误", "GOES 全圆盘仅提供每 10 分钟一个时次，请选择 00、10、20、30、40 或 50 分钟。")],
        )


class TestGUIBuildsWithRealTk(unittest.TestCase):
    """真实 Tk 冒烟：fake 替身无法暴露控件构造参数错误。

    tk 经典控件不接受元组内边距（如 pady=(10, 6)），这类错误只会在建窗口时
    抛 TclError，静态断言和替身测试都发现不了。无图形环境时自动跳过。
    """

    def test_gui_initializes_and_resets_with_real_widgets(self):
        import tkinter as tk

        try:
            root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"无可用图形环境: {error}") from error

        root.withdraw()
        try:
            app = HimawariGUI(root)
            root.update_idletasks()
            root.update()

            # 构造期就应按真实节奏建好时次列表。原先留着创建控件时那 24 个
            # 整点硬编码，界面一打开显示的是"每小时一张"的错误列表。
            self.assertEqual(len(app.time_combo["values"]), 144)
            self.assertIn("时次/10min", app._time_label.cget("text"))

            app.platform_var.set("GOES-18")
            app._on_platform_change(None)
            root.update()
            self.assertEqual(app.region_var.get(), "F (全圆盘)")
            self.assertEqual(len(app.time_combo["values"]), 144)

            app.platform_var.set("Himawari-9")
            app._on_platform_change(None)
            root.update()
            # 全圆盘每 10 分钟一张 → 6 个/小时 × 24
            self.assertEqual(len(app.time_combo["values"]), 144)

            # 切到机动观测：每 2.5 分钟一张 → 24 个/小时 × 24
            app.region_var.set("T (目标区域/机动观测)")
            app._refresh_time_slots()
            root.update()
            self.assertEqual(len(app.time_combo["values"]), 576)
            self.assertIn("00:02:30", app.time_combo["values"])
            self.assertIn("00:05:00", app.time_combo["values"])
            self.assertNotIn("00:00:30", app.time_combo["values"])
            # 关闭状态下输入框显示的时次两种网格里都合法，不展开下拉看不出列表变了，
            # 所以标签必须同步标出当前节奏。
            self.assertIn("时次/2.5min", app._time_label.cget("text"))

            # 切回全圆盘：非网格时次应回落到该小时内第一个合法时次
            app.time_var.set("09:02:30")
            app.region_var.set("F (全圆盘)")
            app._refresh_time_slots()
            root.update()
            self.assertEqual(len(app.time_combo["values"]), 144)
            self.assertNotIn("09:02:30", app.time_combo["values"])
            self.assertEqual(app.time_var.get(), "09:00:00")
            self.assertIn("时次/10min", app._time_label.cget("text"))

            app._clear_image()
            root.update()
            self.assertEqual(app.status_var.get(), "●  就绪")
            self.assertEqual(app.zoom_var.get(), "100%")
        finally:
            root.destroy()

    def test_close_path_cancels_all_pending_callbacks_with_real_tk(self):
        """真实 Tk 下关窗必须把 UI 泵和 matplotlib 的 idle 重绘都取消掉。

        这两处漏一个，窗口销毁后挂着的回调就会触发，报
        `bgerror ... invalid command name`，并且能让 mainloop 不返回
        （窗口没了但进程还在）。fake 替身验证不了，只能真建窗口。
        """
        import tkinter as tk

        try:
            root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"无可用图形环境: {error}") from error

        root.withdraw()
        app = HimawariGUI(root)
        root.update_idletasks()
        # 制造一个 pending 的 idle 重绘，模拟真实使用中"刚重绘完就关窗"
        app.canvas.draw_idle()
        self.assertIsNotNone(app._pump_after_id)
        self.assertIsNotNone(app.canvas._idle_draw_id)

        app._on_close()

        self.assertTrue(app._closing)
        self.assertIsNone(app._pump_after_id)
        self.assertIsNone(app.canvas._idle_draw_id)
        self.assertIsNone(app.canvas._event_loop_id)
        # 窗口确实销毁了：winfo 命令随应用一起消失
        with self.assertRaises(tk.TclError):
            root.winfo_exists()

    def test_date_controls_are_all_mapped_and_clickable(self):
        """年月日三个下拉必须都真实可见、且点击命中的就是它自己。

        历史缺陷：ttk.Combobox 默认按 20 字符索要宽度（约 175px），三个并排需要
        约 525px，而侧栏可用宽度只有约 255px。`pack` 不会把控件压到请求宽度以下，
        于是最后打包的「日」被挤出可视区（winfo_ismapped() 为 0），用户点不到，
        表现为"选不了日期"。

        替身测试和源码断言都发现不了这类问题：控件构造完全正确，是布局把它裁掉了，
        只有真建窗口、真做命中测试才能暴露。
        """
        import tkinter as tk

        try:
            root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"无可用图形环境: {error}") from error

        root.geometry("1280x800+0+0")
        app = HimawariGUI(root)
        try:
            # 窗口位置要在构造之后再定：HimawariGUI.__init__ 会自己设 geometry，
            # 而且同一个进程里反复创建 Tk 时 Windows 会级联下移，窗口可能被推到
            # 屏幕外，winfo_containing 便会返回 None（本用例曾在整套跑时失败、
            # 单跑却通过，就是这个原因）。
            root.geometry("1280x800+0+0")
            root.deiconify()
            root.lift()
            for _ in range(6):
                root.update_idletasks()
                root.update()
            for name, combo in (
                ("year", app.year_combo),
                ("month", app.month_combo),
                ("day", app.day_combo),
            ):
                with self.subTest(control=name):
                    self.assertTrue(combo.winfo_ismapped(), f"{name} 下拉未被显示")
                    self.assertGreater(combo.winfo_width(), 20, f"{name} 宽度异常")
                    # 几何断言：控件右边缘必须落在窗口内，否则就是被裁掉了
                    right_edge = combo.winfo_x() + combo.winfo_width()
                    self.assertLessEqual(
                        right_edge,
                        combo.winfo_toplevel().winfo_width() + 1,
                        f"{name} 超出窗口右边界，会被裁掉",
                    )
                    center_x = combo.winfo_rootx() + combo.winfo_width() // 2
                    center_y = combo.winfo_rooty() + combo.winfo_height() // 2
                    hit = root.winfo_containing(center_x, center_y)
                    if hit is None:
                        # 窗口在本进程里不可见时（被其他窗口遮挡、多屏、CI 无桌面）
                        # Tk 拿不到命中结果。此时上面的几何断言已经覆盖了原始缺陷，
                        # 不再把环境限制误判成产品问题。
                        continue
                    self.assertEqual(str(hit), str(combo), f"{name} 被其它控件遮挡")
        finally:
            app._on_close()


    def test_rail_fits_at_minimum_window_without_clipping(self):
        """右栏内容必须在最小窗口下也放得下。

        历史缺陷：右栏塞了 13 个从未被读取的控件（5 个图层复选框、等值线、
        3 张输出队列卡片），1024×680 时需要 648px 而只有 544px 可用，且右栏
        没有滚动条——底部内容被直接裁掉，用户看不见也点不到。
        """
        import tkinter as tk

        try:
            root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"无可用图形环境: {error}") from error

        root.geometry("1024x680")
        app = HimawariGUI(root)
        try:
            root.update_idletasks()
            root.update()
            inner = app._rail_inner
            self.assertLessEqual(
                inner.winfo_reqheight(), inner.winfo_height(),
                "右栏内容高于可用高度，且右栏没有滚动条，底部控件会被裁掉",
            )
        finally:
            app._on_close()

    def test_sidebar_fits_at_default_window(self):
        """侧栏在默认 1280×800 下应一屏放下，不需要滚动。

        原先是「标签在上、控件在下」的竖排，6 个字段各吃约 72px，连
        1700×960 都要滚动。改内联标签后 1280×800 即可放下。
        """
        import tkinter as tk

        try:
            root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"无可用图形环境: {error}") from error

        root.geometry("1280x800")
        app = HimawariGUI(root)
        try:
            root.update_idletasks()
            root.update()
            canvas = [c for c in app._sidebar.winfo_children()
                      if isinstance(c, tk.Canvas)][0]
            inner = [c for c in canvas.winfo_children()
                     if isinstance(c, tk.Frame)][0]
            self.assertLessEqual(
                inner.winfo_reqheight(), canvas.winfo_height(),
                "侧栏在默认窗口下仍需滚动，说明字段布局又变回了竖排",
            )
        finally:
            app._on_close()

    def test_removed_dead_controls_are_gone(self):
        """13 个空转控件必须彻底移除，不能只从界面上藏起来。

        它们从未被绘制流程读取，留着会误导使用者以为能用。
        只断言标识符与控件文案，不断言叙述性注释——注释里出现"输出队列"
        是在记录这次移除的原因，属于合法历史说明。
        """
        source_path = Path(__file__).resolve().parents[1] / "himawari_gui.py"
        source = source_path.read_text(encoding="utf-8")
        for dead in ("layer_vars", "contour_var", "queue_labels",
                     "ramp_var", "ramp_combo"):
            self.assertNotIn(dead, source, f"空转控件标识符残留：{dead}")
        # 界面文案同样不得残留（这些是用户能看到的字）
        for dead_text in ("'路径追踪'", "'等值线叠加'", '"路径追踪"', '"等值线叠加"'):
            self.assertNotIn(dead_text, source, f"空转控件文案残留：{dead_text}")

    def test_rail_controls_are_wired_into_draw_call(self):
        """右栏保留的三个控件必须真的传给引擎，而不是只放在界面上。"""
        draw_image_source = inspect.getsource(HimawariGUI._draw_image)
        worker_source = inspect.getsource(HimawariGUI._draw_worker)
        self.assertIn("_read_range_inputs", draw_image_source)
        self.assertIn("reverse_var", draw_image_source)
        # 三个着色参数必须出现在引擎调用里
        self.assertIn("vmin=vmin", worker_source)
        self.assertIn("vmax=vmax", worker_source)
        self.assertIn("reverse_cmap=reverse_cmap", worker_source)

    def test_range_inputs_default_to_none_and_validate(self):
        """温度范围留空 = 用色阶表自带范围；填错必须报错而不是静默忽略。"""
        app = object.__new__(HimawariGUI)

        class _Var:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        app.vmin_var = _Var('')
        app.vmax_var = _Var('')
        self.assertEqual(HimawariGUI._read_range_inputs(app), (None, None))

        app.vmin_var = _Var('-50')
        app.vmax_var = _Var('10')
        self.assertEqual(HimawariGUI._read_range_inputs(app), (-50.0, 10.0))

        app.vmin_var = _Var('abc')
        with self.assertRaises(ValueError):
            HimawariGUI._read_range_inputs(app)

        # 下限不小于上限必须报错，否则 Normalize 会得到非法区间
        app.vmin_var = _Var('10')
        app.vmax_var = _Var('10')
        with self.assertRaises(ValueError):
            HimawariGUI._read_range_inputs(app)

    def test_palette_meets_wcag_aa_contrast(self):
        """主题令牌的对比度必须达标，否则文字看不清。

        历史问题：浅色 text_subtle=#9ca3af 对白底只有 2.54（AA 需 4.5），
        被用在状态栏、字段标签、色带刻度上；深色主按钮白字只有 3.68。
        """
        def luminance(hex_color):
            raw = hex_color.lstrip('#')
            channels = [int(raw[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                      for c in channels]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        def contrast(fg, bg):
            a, b = luminance(fg), luminance(bg)
            high, low = max(a, b), min(a, b)
            return (high + 0.05) / (low + 0.05)

        for theme_name, palette in (("light", light_palette()), ("dark", dark_palette())):
            for label, fg, bg in (
                ("正文", palette['text'], palette['panel']),
                ("次要", palette['text_secondary'], palette['panel']),
                ("弱化", palette['text_muted'], palette['panel']),
                ("最弱", palette['text_subtle'], palette['panel']),
                ("主按钮文字", palette['primary_fg'], palette['primary']),
            ):
                with self.subTest(theme=theme_name, token=label):
                    self.assertGreaterEqual(
                        contrast(fg, bg), 4.5,
                        f"{theme_name} 主题的{label}对比度不足：{fg} on {bg}",
                    )


    def test_display_image_builds_bounded_preview_base(self):
        """载入图片时必须建好预览基准图，且不超过画布 2 倍。

        没有这张基准图，缩放每格都要从几千像素的原图重缩，交互会明显卡顿。
        """
        import tkinter as tk
        from PIL import Image

        try:
            root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"无可用图形环境: {error}") from error

        root.geometry("1280x800+0+0")
        app = HimawariGUI(root)
        img_path = Path(__file__).resolve().parents[1] / "data" / "sample_for_test.png"
        try:
            root.update_idletasks()
            root.update()
            Image.new('RGB', (4000, 3000), (30, 40, 50)).save(img_path)

            app.current_image_path = str(img_path)
            app._display_image(None, 'IR-WK')
            root.update()

            self.assertIsNotNone(app._preview_base, "未建立预览基准图")
            canvas = app.canvas.get_tk_widget()
            limit = max(canvas.winfo_width(), canvas.winfo_height()) * 2
            self.assertLessEqual(app._preview_base.width, max(limit, 1))
            self.assertLessEqual(app._preview_base.height, max(limit, 1))
            # 基准图必须保留原图比例
            self.assertAlmostEqual(
                app._preview_base.width / app._preview_base.height,
                4000 / 3000,
                places=2,
            )
        finally:
            app._on_close()
            if img_path.exists():
                img_path.unlink()


if __name__ == "__main__":
    unittest.main()

import inspect
from pathlib import Path
import queue
import unittest
from unittest.mock import patch

from himawari_ir_toolkit.himawari_gui import HimawariGUI, PLATFORM_OPTIONS, _platform_identifier


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

    def after(self, delay, callback, *args):
        self.after_calls.append((delay, callback, args))

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
            "日期时间 (UTC)",
            "绘制云图",
            "保存图片",
            "清空",
        ):
            self.assertIn(value, source)

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
            ("'success'", "SUCCESS", "#059669"),
            ("'error'", "ERROR", "#dc2626"),
            ("'text_subtle'", "TEXT_SUBTLE", "#9ca3af"),
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

            def resize(self, _size, _resample):
                return self.resized_image

        class _Canvas:
            def get_tk_widget(self):
                return self

            def create_image(self, *_args, **_kwargs):
                return 1

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

    def test_platform_change_back_to_himawari_restores_hourly_times(self):
        app = self._platform_app("Himawari-9", "09:30:00")

        HimawariGUI._on_platform_change(app, None)

        self.assertEqual(len(app.time_combo.values), 24)
        self.assertEqual(app.time_combo.values[0], "00:00:00")
        self.assertEqual(app.time_combo.values[-1], "23:00:00")
        self.assertEqual(app.time_var.get(), "09:00:00")

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
        self.assertEqual(started[0][1][-1], "GOES-19")

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

            app.platform_var.set("GOES-18")
            app._on_platform_change(None)
            root.update()
            self.assertEqual(app.region_var.get(), "F (全圆盘)")
            self.assertEqual(len(app.time_combo["values"]), 144)

            app.platform_var.set("Himawari-9")
            app._on_platform_change(None)
            root.update()
            self.assertEqual(len(app.time_combo["values"]), 24)

            app._clear_image()
            root.update()
            self.assertEqual(app.status_var.get(), "●  就绪")
            self.assertEqual(app.zoom_var.get(), "100%")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()

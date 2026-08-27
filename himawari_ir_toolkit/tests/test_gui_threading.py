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
            "Himawari / GOES 卫星云图分析工具",
            "UTC 数据选择 · 卫星云图绘制",
            "时间与卫星",
            "数据与显示",
            "绘制与输出",
            "日期时间 (UTC)",
            "绘制云图",
            "保存图片",
            "清空",
        ):
            self.assertIn(value, source)

    def test_control_panel_uses_compact_fixed_row_spacing(self):
        source_path = Path(__file__).resolve().parents[1] / "himawari_gui.py"
        source = source_path.read_text(encoding="utf-8")

        for value in (
            "datetime_frame.pack(fill=tk.X, pady=(0, 8))",
            "platform_frame.pack(fill=tk.X, pady=(0, 8))",
            "type_frame.pack(fill=tk.X, pady=(0, 8))",
            "band_frame.pack(fill=tk.X, pady=(0, 8))",
            "scheme_frame.pack(fill=tk.X, pady=(0, 8))",
            "region_frame.pack(fill=tk.X, pady=(0, 10))",
        ):
            self.assertIn(value, source)

        self.assertEqual(source.count("style='Section.TLabel').pack(anchor=tk.W, pady=(0, 6))"), 3)

    def test_setup_styles_uses_bright_research_palette(self):
        source_path = Path(__file__).resolve().parents[1] / "himawari_gui.py"
        source = source_path.read_text(encoding="utf-8")

        for value in ("#243447", "#607080", "#1769AA", "Segoe UI"):
            self.assertIn(value, source)
        self.assertNotIn("foreground='#000000'", source)
        self.assertNotIn("text_color='#000000'", source)
        for value in ("Primary.TButton", "Secondary.TButton", "Danger.TButton", "#FDECEC"):
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

        expected_foregrounds = {
            "Primary.TButton": ("#607080", "white"),
            "Secondary.TButton": ("#607080", "#243447"),
            "Danger.TButton": ("#607080", "#9B2C2C"),
        }
        for style_name, (disabled, enabled) in expected_foregrounds.items():
            map_start = source.index(f"style.map('{style_name}'")
            map_end = source.index("\n                  relief=", map_start)
            style_map = source[map_start:map_end]
            self.assertIn(
                f"foreground=[('disabled', '{disabled}'), ('!disabled', '{enabled}')]",
                style_map,
            )

    def test_status_feedback_defines_four_states_and_uses_each_lifecycle_state(self):
        source_path = Path(__file__).resolve().parents[1] / "himawari_gui.py"
        source = source_path.read_text(encoding="utf-8")
        clear_image_source = inspect.getsource(HimawariGUI._clear_image)
        draw_image_source = inspect.getsource(HimawariGUI._draw_image)
        success_source = inspect.getsource(HimawariGUI._on_draw_success)
        error_source = inspect.getsource(HimawariGUI._on_draw_error)

        for value in (
            "Working.Progress.TLabel",
            "Success.Progress.TLabel",
            "Error.Progress.TLabel",
            "Ready.Progress.TLabel",
            "after",
            "after_cancel",
            "#1769AA",
            "#2E7D32",
            "#B42318",
            "#607080",
        ):
            self.assertIn(value, source)
        self.assertIn("_show_status_feedback('Working'", draw_image_source)
        self.assertIn("_show_status_feedback('Success'", success_source)
        self.assertIn("_show_status_feedback('Error'", error_source)
        self.assertIn("_show_status_feedback('Ready'", clear_image_source)
        self.assertNotIn("_show_status_feedback('Success', \"就绪\")", clear_image_source)
        self.assertIn("Progress.TLabel", source[source.index("Working.Progress.TLabel"):])
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

        with patch("himawari_ir_toolkit.himawari_gui._debug_report", lambda *a, **k: None):
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
        def update(self):
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
        source = inspect.getsource(HimawariGUI._init_ui)
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


if __name__ == "__main__":
    unittest.main()

import ast
import importlib
import io
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from himawari_ir_toolkit.draw_ir_fulldisk import DATA_TYPES, _download_s3_files_with_progress
from himawari_ir_toolkit.mycolor import my_color_map


class _FakeReader(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _FakeS3:
    def __init__(self):
        self.files = {
            "first": b"abcd",
            "second": b"efghij",
        }

    def info(self, path):
        return {"size": len(self.files[path])}

    def open(self, path, mode):
        self.assertEqual(mode, "rb")
        return _FakeReader(self.files[path])

    def assertEqual(self, actual, expected):
        if actual != expected:
            raise AssertionError(f"expected {expected!r}, got {actual!r}")


class TestDownloadProgress(unittest.TestCase):
    def test_script_mode_adds_package_root_and_uses_package_imports(self):
        script_path = Path(__file__).resolve().parents[1] / "draw_ir_fulldisk.py"
        tree = ast.parse(script_path.read_text(encoding="utf-8"))
        script_branch = next(
            node for node in tree.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "__package__"
        ).orelse

        package_root = next(
            node for node in script_branch
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "PACKAGE_ROOT"
        )
        self.assertEqual(
            ast.unparse(package_root.value),
            "os.path.dirname(os.path.dirname(os.path.abspath(__file__)))",
        )
        path_insert = next(
            node for node in ast.walk(ast.Module(body=script_branch, type_ignores=[]))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "sys"
            and node.func.value.attr == "path"
            and node.func.attr == "insert"
        )
        self.assertEqual(ast.unparse(path_insert.args[1]), "PACKAGE_ROOT")
        imported_modules = {
            node.module
            for node in ast.walk(ast.Module(body=script_branch, type_ignores=[]))
            if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("himawari_ir_toolkit.mycolor", imported_modules)
        self.assertIn("himawari_ir_toolkit.satellite_providers", imported_modules)
        self.assertNotIn("mycolor", imported_modules)
        self.assertNotIn("satellite_providers", imported_modules)

    def test_cli_list_exits_before_drawing(self):
        module = importlib.import_module("himawari_ir_toolkit.draw_ir_fulldisk")
        with patch.object(module, "list_schemes") as list_schemes, patch.object(
            module, "draw_ir_fulldisk"
        ) as draw, patch.object(sys, "argv", ["draw_ir_fulldisk.py", "--list"]):
            with self.assertRaises(SystemExit) as exit_context:
                module.main()

        self.assertEqual(exit_context.exception.code, 0)
        list_schemes.assert_called_once_with()
        draw.assert_not_called()

    def test_package_import_uses_package_satellite_provider(self):
        module = importlib.import_module("himawari_ir_toolkit.draw_ir_fulldisk")

        self.assertEqual(
            module.get_provider_config.__module__,
            "himawari_ir_toolkit.satellite_providers",
        )

    def test_cli_platform_is_forwarded_to_draw(self):
        module = importlib.import_module("himawari_ir_toolkit.draw_ir_fulldisk")
        with patch.object(module, "draw_ir_fulldisk") as draw, patch.object(
            sys, "argv", ["draw_ir_fulldisk.py", "--platform", "GOES-19"]
        ):
            module.main()

        self.assertEqual(draw.call_args.kwargs["platform"], "GOES-19")

    def test_cli_platform_help_describes_goes_limits_and_wv_avg_band(self):
        module = importlib.import_module("himawari_ir_toolkit.draw_ir_fulldisk")
        parser = module.build_parser()

        help_text = parser.format_help()
        self.assertIn("GOES 限全圆盘和十分钟 UTC 槽位", help_text)
        self.assertIn("WV AVG", help_text)
        self.assertEqual(parser.parse_args([]).platform, "Himawari-9")

    def test_build_scene_title_uses_platform_and_source_channels(self):
        from himawari_ir_toolkit.draw_ir_fulldisk import build_scene_title

        goes_scene = SimpleNamespace(
            platform="GOES-19", logical_band="AVG", source_channels=("C08", "C09")
        )
        himawari_scene = SimpleNamespace(
            platform="Himawari-9", logical_band="B14", source_channels=("B14",)
        )

        self.assertEqual(build_scene_title(goes_scene, "WV"), "GOES-19 WV AVG (C08/C09)")
        self.assertEqual(build_scene_title(himawari_scene, "IR"), "Himawari-9 IR B14 (B14)")

    def test_build_scene_geostationary_crs_uses_scene_projection_metadata(self):
        from himawari_ir_toolkit.draw_ir_fulldisk import build_scene_geostationary_crs

        projection = SimpleNamespace(
            perspective_point_height=35786023,
            longitude_of_projection_origin=-137.2,
            sweep_angle_axis="x",
            semi_major_axis=6378137.0,
            semi_minor_axis=6356752.31414,
        )
        scene = SimpleNamespace(projection=projection)
        globe = object()
        crs = object()

        with patch("himawari_ir_toolkit.draw_ir_fulldisk.ccrs.Globe", return_value=globe) as globe_class, patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.ccrs.Geostationary", return_value=crs
        ) as geostationary_class:
            self.assertIs(build_scene_geostationary_crs(scene), crs)

        globe_class.assert_called_once_with(
            semimajor_axis=6378137.0,
            semiminor_axis=6356752.31414,
        )
        geostationary_class.assert_called_once_with(
            central_longitude=-137.2,
            satellite_height=35786023,
            sweep_axis="x",
            globe=globe,
        )

    def test_draw_satellite_scene_renders_scene_data_with_scene_projection_and_title(self):
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_satellite_scene

        scene = SimpleNamespace(
            data=np.array([[1.0, 2.0], [3.0, 4.0]]),
            x_scan_rad=np.array([-0.1, 0.1]),
            y_scan_rad=np.array([-0.2, 0.2]),
            platform="GOES-19",
            logical_band="AVG",
            source_channels=("C08", "C09"),
            unit_kind="brightness_temperature",
            region="FLDK",
            projection=SimpleNamespace(perspective_point_height=35786023),
        )
        crs = object()
        cmap = object()
        norm = SimpleNamespace(vmin=-100.0, vmax=50.0)
        fig = MagicMock()
        ax = MagicMock()
        fig.add_subplot.return_value = ax
        ax.get_position.return_value = SimpleNamespace(x0=0.01, x1=0.9, y0=0.01, y1=0.9, height=0.89)

        with patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.build_scene_geostationary_crs", return_value=crs
        ) as build_crs, patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.build_scene_title", return_value="GOES-19 WV AVG (C08/C09)"
        ) as build_title, patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.my_color_map", return_value=(cmap, norm)
        ), patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.plt.figure", return_value=fig
        ), patch("himawari_ir_toolkit.draw_ir_fulldisk.plt.close") as close:
            result = draw_satellite_scene(scene, "WV", "scene.png", 100, add_decorations=True)

        self.assertEqual(result[0], "scene.png")
        self.assertIs(result[1], scene.data)
        self.assertTrue(np.allclose(result[2], (-3578602.3, 3578602.3, -7157204.6, 7157204.6)))
        build_crs.assert_called_once_with(scene)
        build_title.assert_called_once_with(scene, "WV")
        fig.add_subplot.assert_called_once_with(1, 1, 1, projection=crs)
        ax.imshow.assert_called_once()
        imshow_args, imshow_kwargs = ax.imshow.call_args
        self.assertIs(imshow_args[0], scene.data)
        self.assertTrue(np.allclose(
            imshow_kwargs["extent"],
            (-3578602.3, 3578602.3, -7157204.6, 7157204.6),
        ))
        self.assertEqual(imshow_kwargs["origin"], "upper")
        self.assertIs(imshow_kwargs["cmap"], cmap)
        self.assertIs(imshow_kwargs["norm"], norm)
        self.assertEqual(imshow_kwargs["interpolation"], "none")
        fig.text.assert_called_once_with(0.01, 0.99, "GOES-19 WV AVG (C08/C09)", ha="left", va="bottom")
        fig.savefig.assert_called_once_with("scene.png", dpi=100, bbox_inches=None, facecolor="white", edgecolor="none")
        close.assert_called_once_with(fig)

    def test_draw_satellite_scene_closes_figure_when_save_fails(self):
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_satellite_scene

        scene = SimpleNamespace(
            data=np.array([[1.0, 2.0], [3.0, 4.0]]),
            x_scan_rad=np.array([-0.1, 0.1]),
            y_scan_rad=np.array([-0.2, 0.2]),
            region="FLDK",
            projection=SimpleNamespace(perspective_point_height=35786023),
        )
        fig = MagicMock()
        fig.add_subplot.return_value = MagicMock()
        fig.savefig.side_effect = OSError("disk full")

        with patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.build_scene_geostationary_crs", return_value=object()
        ), patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.my_color_map", return_value=(object(), object())
        ), patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.plt.figure", return_value=fig
        ), patch("himawari_ir_toolkit.draw_ir_fulldisk.plt.close") as close:
            with self.assertRaisesRegex(OSError, "disk full"):
                draw_satellite_scene(scene, "WV", "scene.png", 100)

        close.assert_called_once_with(fig)

    def test_extract_render_inputs_closes_dataset_after_copying_arrays(self):
        from himawari_ir_toolkit.draw_ir_fulldisk import _extract_render_inputs

        class _Value:
            def __init__(self, values):
                self.values = values

        class _Dataset:
            def __init__(self):
                self.values = np.array([[[273.15, 274.15]]])
                self.closed = False
                self.coords = {"x": _Value(np.array([1.0, 2.0])), "y": _Value(np.array([3.0]))}

            def __getitem__(self, key):
                return self.coords[key]

            def close(self):
                self.closed = True

        dataset = _Dataset()
        data, x_scan, y_scan = _extract_render_inputs(dataset, "B14", True)

        self.assertTrue(dataset.closed)
        self.assertTrue(np.array_equal(data, np.array([[0.0, 1.0]])))
        self.assertTrue(np.array_equal(x_scan, np.array([1.0, 2.0])))
        self.assertTrue(np.array_equal(y_scan, np.array([3.0])))

    def test_draw_entry_loads_and_draws_goes_scene_with_actual_scan_time_output_name(self):
        from datetime import datetime
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_ir_fulldisk

        scene = SimpleNamespace(scan_start=datetime(2026, 8, 7, 12, 30, 17))
        result = ("data/goes-18_IR_B14_FLDK_2026-08-07_123017_IR-CC.png", object(), object())
        with patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.load_goes_scene", return_value=scene
        ) as load_goes_scene, patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.draw_satellite_scene", return_value=result
        ) as draw_scene, patch.dict(sys.modules, {"pycontrails": None}):
            actual = draw_ir_fulldisk(
                "2026-08-07T12:30:00", "IR-CC", dpi=100, platform="GOES-18",
                band="B14", add_decorations=True, progress_callback=object(),
            )

        self.assertIs(actual, result)
        load_goes_scene.assert_called_once_with(
            "GOES-18", datetime(2026, 8, 7, 12, 30), "IR", "B14"
        )
        draw_scene.assert_called_once()
        draw_args, draw_kwargs = draw_scene.call_args
        self.assertIs(draw_args[0], scene)
        self.assertEqual(draw_args[1], "IR-CC")
        self.assertEqual(Path(draw_args[2]).as_posix(), result[0])
        self.assertEqual(draw_args[3], 100)
        self.assertTrue(draw_kwargs["add_decorations"])
        self.assertIsNotNone(draw_kwargs["progress_callback"])

    def test_draw_entry_routes_historical_goes_platforms_to_goes_loader(self):
        from datetime import datetime
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_ir_fulldisk

        for platform, requested_time in (
            ("GOES-16", "2020-01-01T12:30:00"),
            ("GOES-17", "2022-01-01T12:30:00"),
        ):
            with self.subTest(platform=platform), patch(
                "himawari_ir_toolkit.draw_ir_fulldisk.load_goes_scene",
                return_value=SimpleNamespace(scan_start=datetime(2022, 1, 1, 12, 30)),
            ) as load_goes_scene, patch(
                "himawari_ir_toolkit.draw_ir_fulldisk.draw_satellite_scene",
                return_value=("scene.png", object(), object()),
            ) as draw_scene, patch.dict(sys.modules, {"pycontrails": None}):
                draw_ir_fulldisk(requested_time, "IR-CC", dpi=100, platform=platform, band="B14")

            load_goes_scene.assert_called_once_with(platform, datetime.fromisoformat(requested_time), "IR", "B14")
            draw_scene.assert_called_once()

    def test_draw_entry_routes_goes_16_2024_archive_date_to_goes_loader(self):
        from datetime import datetime
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_ir_fulldisk

        scene = SimpleNamespace(scan_start=datetime(2024, 8, 1, 12, 0))
        result = ("scene.png", object(), object())
        with patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.load_goes_scene", return_value=scene
        ) as load_goes_scene, patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.draw_satellite_scene", return_value=result
        ) as draw_scene, patch.dict(sys.modules, {"pycontrails": None}):
            actual = draw_ir_fulldisk(
                "2024-08-01T12:00:00", "IR-CC", dpi=100,
                platform="GOES-16", band="B14",
            )

        self.assertIs(actual, result)
        load_goes_scene.assert_called_once_with(
            "GOES-16", datetime(2024, 8, 1, 12, 0), "IR", "B14"
        )
        draw_scene.assert_called_once()

    def test_draw_entry_routes_goes_17_archive_date_to_goes_loader(self):
        from datetime import datetime
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_ir_fulldisk

        scene = SimpleNamespace(scan_start=datetime(2022, 8, 1, 12, 0))
        result = ("scene.png", object(), object())
        with patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.load_goes_scene", return_value=scene
        ) as load_goes_scene, patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.draw_satellite_scene", return_value=result
        ) as draw_scene, patch.dict(sys.modules, {"pycontrails": None}):
            actual = draw_ir_fulldisk(
                "2022-08-01T12:00:00", "IR-CC", dpi=100,
                platform="GOES-17", band="B14",
            )

        self.assertIs(actual, result)
        load_goes_scene.assert_called_once_with(
            "GOES-17", datetime(2022, 8, 1, 12, 0), "IR", "B14"
        )
        draw_scene.assert_called_once()

    def test_draw_entry_converts_offset_goes_time_to_naive_utc_before_loading(self):
        from datetime import datetime
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_ir_fulldisk

        scene = SimpleNamespace(scan_start=datetime(2026, 8, 7, 12, 30))
        with patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.load_goes_scene", return_value=scene
        ) as load_goes_scene, patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.draw_satellite_scene", return_value=("scene.png", object(), object())
        ) as draw_scene:
            draw_ir_fulldisk(
                "2026-08-07T20:30:00+08:00", "IR-CC", dpi=100,
                platform="GOES-18", band="B14",
            )

        load_goes_scene.assert_called_once_with(
            "GOES-18", datetime(2026, 8, 7, 12, 30), "IR", "B14"
        )
        draw_scene.assert_called_once()

    def test_draw_entry_goes_preserves_explicit_output_path(self):
        from datetime import datetime
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_ir_fulldisk

        scene = SimpleNamespace(scan_start=datetime(2026, 8, 7, 12, 30, 17))
        with patch("himawari_ir_toolkit.draw_ir_fulldisk.load_goes_scene", return_value=scene), patch(
            "himawari_ir_toolkit.draw_ir_fulldisk.draw_satellite_scene", return_value=("custom.png", object(), object())
        ) as draw_scene:
            draw_ir_fulldisk(
                "2026-08-07T12:30:00", "IR-CC", out_path="custom.png", platform="GOES-19", band="B14"
            )

        self.assertEqual(draw_scene.call_args.args[2], "custom.png")

    def test_draw_entry_rejects_goes_archive_date_before_loading(self):
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_ir_fulldisk

        with patch("himawari_ir_toolkit.draw_ir_fulldisk.load_goes_scene") as load_goes_scene:
            with self.assertRaisesRegex(ValueError, "GOES-19.*2025-04-07.*至今.*2024-08-01"):
                draw_ir_fulldisk(
                    "2024-08-01T09:00:00", "IR-CC", platform="GOES-19", band="B14"
                )

        load_goes_scene.assert_not_called()

    def test_draw_entry_rejects_invalid_goes_inputs_before_loading(self):
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_ir_fulldisk

        cases = [
            ({"platform": "unknown"}, "Unknown platform"),
            ({"platform": "GOES-18", "region": "T"}, "Invalid region"),
            ({"platform": "GOES-18", "time_str": "2026-08-07T12:35:00"}, "Invalid CMIPF slot"),
            ({"platform": "GOES-18", "time_str": "2026-08-07T12:30:01"}, "Invalid CMIPF slot"),
            ({"platform": "GOES-18", "data_type": "NOPE"}, "Unknown data_type"),
            ({"platform": "GOES-18", "band": "B08"}, "Invalid band"),
            ({"platform": "GOES-18", "scheme": "WV"}, "Invalid scheme"),
            ({"platform": "GOES-18", "time_str": "not-a-time"}, "Invalid time_str"),
        ]
        with patch("himawari_ir_toolkit.draw_ir_fulldisk.load_goes_scene") as load_goes_scene:
            for kwargs, message in cases:
                with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, message):
                    draw_ir_fulldisk(**kwargs)

        load_goes_scene.assert_not_called()

    def test_draw_entry_rejects_unknown_data_type_before_download(self):
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_ir_fulldisk

        with self.assertRaisesRegex(ValueError, "Unknown data_type"):
            draw_ir_fulldisk(data_type="NOPE")

    def test_draw_entry_rejects_invalid_band_scheme_and_region(self):
        from himawari_ir_toolkit.draw_ir_fulldisk import draw_ir_fulldisk

        for kwargs, text in [
            ({"data_type": "IR", "band": "B08"}, "Invalid band"),
            ({"data_type": "IR", "scheme": "WV"}, "Invalid scheme"),
            ({"data_type": "IR", "region": "X"}, "Invalid region"),
        ]:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, text):
                    draw_ir_fulldisk(**kwargs)

    def test_wv_type_change_uses_configured_default_scheme(self):
        from himawari_ir_toolkit.himawari_gui import HimawariGUI

        app = object.__new__(HimawariGUI)
        app.data_type_var = type("Var", (), {"get": lambda self: "WV (水汽)"})()
        app.band_combo = type("Combo", (), {"__setitem__": lambda self, key, value: None})()
        app.scheme_combo = type("Combo", (), {"__setitem__": lambda self, key, value: None})()
        app.band_var = type("Var", (), {"set": lambda self, value: setattr(self, "value", value)})()
        app.scheme_var = type("Var", (), {"set": lambda self, value: setattr(self, "value", value)})()

        HimawariGUI._on_type_change(app, None)

        self.assertEqual(app.scheme_var.value, DATA_TYPES["WV"]["default_scheme"])

    def test_wv_avg_is_a_band_and_classic_wv_and_ssd_are_schemes(self):
        self.assertEqual(DATA_TYPES["WV"]["bands"], ["B08", "B09", "AVG"])
        self.assertEqual(DATA_TYPES["WV"]["schemes"], ["WV", "WV-SSD"])
        self.assertEqual(DATA_TYPES["WV"]["default_scheme"], "WV")
        cmap, norm = my_color_map("WV")
        self.assertEqual(cmap.name, "WV")
        self.assertEqual(norm.vmin, -100)

    def test_streamed_download_reports_total_and_incremental_bytes(self):
        events = []

        downloaded = _download_s3_files_with_progress(
            _FakeS3(),
            ["first", "second"],
            lambda downloaded_bytes, total_bytes, file_index, file_count: events.append(
                (downloaded_bytes, total_bytes, file_index, file_count)
            ),
            chunk_size=3,
        )

        self.assertEqual(downloaded, [b"abcd", b"efghij"])
        self.assertEqual(events[0], (0, 10, 0, 2))
        self.assertIn((4, 10, 1, 2), events)
        self.assertEqual(events[-1], (10, 10, 2, 2))

    def test_streamed_download_keeps_global_progress_across_groups(self):
        events = []
        fs = _FakeS3()

        _download_s3_files_with_progress(
            fs,
            ["first"],
            lambda *event: events.append(event),
            total_bytes=10,
            file_count=2,
            chunk_size=3,
        )
        _download_s3_files_with_progress(
            fs,
            ["second"],
            lambda *event: events.append(event),
            total_bytes=10,
            initial_bytes=4,
            file_offset=1,
            file_count=2,
            announce_start=False,
            chunk_size=3,
        )

        self.assertEqual(events[-1], (10, 10, 2, 2))
        self.assertEqual([event[0] for event in events], sorted(event[0] for event in events))

    def test_streamed_download_rejects_silent_short_reads_after_three_attempts(self):
        class ShortReadS3(_FakeS3):
            def __init__(self):
                super().__init__()
                self.open_count = 0

            def info(self, path):
                return {"size": len(self.files[path])}

            def open(self, path, mode):
                self.open_count += 1
                return _FakeReader(self.files[path][:-1])

        fs = ShortReadS3()
        with self.assertRaisesRegex(ValueError, r"first.*expected 4.*actual 3"):
            _download_s3_files_with_progress(fs, ["first"], lambda *_event: None)

        self.assertEqual(fs.open_count, 3)

    def test_streamed_download_retries_after_truncated_response(self):
        class FlakyReader(_FakeReader):
            def __init__(self, data, fail):
                super().__init__(data)
                self.fail = fail

            def read(self, size=-1):
                if self.fail:
                    raise ConnectionError("truncated response")
                return super().read(size)

        class FlakyS3(_FakeS3):
            def __init__(self):
                super().__init__()
                self.open_count = 0

            def open(self, path, mode):
                self.open_count += 1
                return FlakyReader(self.files[path], fail=self.open_count == 1)

        fs = FlakyS3()
        downloaded = _download_s3_files_with_progress(
            fs,
            ["first"],
            lambda *_event: None,
            chunk_size=3,
        )

        self.assertEqual(downloaded, [b"abcd"])
        self.assertEqual(fs.open_count, 2)


if __name__ == "__main__":
    unittest.main()

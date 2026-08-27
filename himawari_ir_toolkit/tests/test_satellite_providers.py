from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime
import inspect
import unittest

import numpy as np

from himawari_ir_toolkit.satellite_scene import ProjectionMetadata, Scene
from himawari_ir_toolkit.satellite_providers import (
    PROVIDER_CONFIGS,
    _parse_goes_scan_object,
    get_archive_window,
    get_platform_label,
    get_provider_config,
    get_source_channels,
    goes_cmipf_prefix,
    load_goes_scene,
    validate_archive_date,
    select_goes_scan_object,
    scene_from_goes_datasets,
)


class TestProviderConfig(unittest.TestCase):
    def test_provider_configs_include_exact_identifiers_labels_and_archive_boundaries(self):
        goes_minutes = (0, 10, 20, 30, 40, 50)
        expected = {
            "GOES-16": ("noaa-goes16", "GOES-16", date(2017, 12, 18), date(2025, 4, 6)),
            "GOES-17": ("noaa-goes17", "GOES-17（历史）", date(2018, 12, 4), date(2023, 1, 10)),
            "GOES-18": ("noaa-goes18", "GOES-18", date(2023, 1, 4), None),
            "GOES-19": ("noaa-goes19", "GOES-19", date(2025, 4, 7), None),
        }
        self.assertEqual(set(PROVIDER_CONFIGS), {"Himawari-9", *expected})
        for identifier, (bucket, label, archive_start, archive_end) in expected.items():
            with self.subTest(identifier=identifier):
                config = PROVIDER_CONFIGS[identifier]
                self.assertEqual(config.regions, ("F",))
                self.assertEqual(config.minutes, goes_minutes)
                self.assertEqual(config.bucket, bucket)
                self.assertEqual(config.label, label)
                self.assertEqual(config.archive_start, archive_start)
                self.assertEqual(config.archive_end, archive_end)

        himawari = PROVIDER_CONFIGS["Himawari-9"]
        self.assertEqual(himawari.regions, ("F", "T"))
        self.assertEqual(himawari.minutes, (0,))
        self.assertIsNone(himawari.bucket)
        self.assertEqual(himawari.label, "Himawari-9")
        self.assertIsNone(himawari.archive_start)
        self.assertIsNone(himawari.archive_end)

    def test_platform_labels_and_archive_windows(self):
        expected = {
            "GOES-16": ("GOES-16", (date(2017, 12, 18), date(2025, 4, 6))),
            "GOES-17": ("GOES-17（历史）", (date(2018, 12, 4), date(2023, 1, 10))),
            "GOES-18": ("GOES-18", (date(2023, 1, 4), None)),
            "GOES-19": ("GOES-19", (date(2025, 4, 7), None)),
            "Himawari-9": ("Himawari-9", (None, None)),
        }
        for identifier, (label, archive_window) in expected.items():
            with self.subTest(identifier=identifier):
                self.assertEqual(get_platform_label(identifier), label)
                self.assertEqual(get_archive_window(identifier), archive_window)

    def test_unknown_platform_behavior_is_unchanged(self):
        self.assertEqual(get_provider_config("GOES-19"), PROVIDER_CONFIGS["GOES-19"])
        with self.assertRaises(ValueError):
            get_provider_config("unknown")

    def test_goes_source_channel_mapping(self):
        expected = {
            ("IR", "B13"): ("C13",),
            ("IR", "B14"): ("C14",),
            ("WV", "B08"): ("C08",),
            ("WV", "B09"): ("C09",),
            ("WV", "AVG"): ("C08", "C09"),
            ("VIS", "B03"): ("C02",),
        }
        for key, channels in expected.items():
            self.assertEqual(get_source_channels("GOES-18", *key), channels)
        self.assertEqual(
            get_source_channels("GOES-18", data_type="IR", band="B14"),
            ("C14",),
        )
        self.assertEqual(
            list(inspect.signature(get_source_channels).parameters),
            ["platform", "data_type", "band"],
        )
        with self.assertRaises(ValueError):
            get_source_channels("GOES-18", "IR", "B99")

    def test_source_channels_support_all_configured_goes_and_reject_non_goes(self):
        self.assertEqual(get_source_channels("GOES-16", "IR", "B14"), ("C14",))
        self.assertEqual(get_source_channels("GOES-17", "WV", "AVG"), ("C08", "C09"))
        with self.assertRaises(ValueError):
            get_source_channels("Himawari-9", "IR", "B14")
        with self.assertRaises(ValueError):
            get_source_channels("GOES-20", "IR", "B14")


class TestArchiveDateValidation(unittest.TestCase):
    def test_goes_16_and_17_product_boundaries(self):
        for requested in (datetime(2024, 8, 1), datetime(2025, 4, 6)):
            with self.subTest(platform="GOES-16", requested=requested):
                self.assertIsNone(validate_archive_date("GOES-16", requested))
        with self.assertRaises(ValueError):
            validate_archive_date("GOES-16", datetime(2025, 4, 7))
        self.assertIsNone(validate_archive_date("GOES-17", datetime(2023, 1, 10)))
        with self.assertRaises(ValueError):
            validate_archive_date("GOES-17", datetime(2023, 1, 11))

    def test_archive_boundaries_and_himawari_window(self):
        accepted = {
            "GOES-16": (datetime(2017, 12, 18), datetime(2025, 4, 6)),
            "GOES-17": (datetime(2018, 12, 4), datetime(2023, 1, 10)),
            "GOES-18": (datetime(2023, 1, 4), datetime(2026, 8, 8)),
            "GOES-19": (datetime(2025, 4, 7), datetime(2026, 8, 8)),
            "Himawari-9": (datetime(1900, 1, 1), datetime(2100, 1, 1)),
        }
        for platform, (start, end) in accepted.items():
            with self.subTest(platform=platform):
                self.assertIsNone(validate_archive_date(platform, start))
                self.assertIsNone(validate_archive_date(platform, end))

    def test_archive_out_of_range_error_contains_window_and_request(self):
        cases = [
            ("GOES-16", datetime(2017, 12, 17), "2017-12-18", "2025-04-06"),
            ("GOES-16", datetime(2025, 4, 7), "2017-12-18", "2025-04-06"),
            ("GOES-17", datetime(2018, 12, 3), "2018-12-04", "2023-01-10"),
            ("GOES-17", datetime(2023, 1, 11), "2018-12-04", "2023-01-10"),
            ("GOES-18", datetime(2023, 1, 3), "2023-01-04", "至今"),
            ("GOES-19", datetime(2025, 4, 6), "2025-04-07", "至今"),
        ]
        for platform, requested, start, end in cases:
            with self.subTest(platform=platform):
                with self.assertRaisesRegex(ValueError, platform):
                    validate_archive_date(platform, requested)
                try:
                    validate_archive_date(platform, requested)
                except ValueError as error:
                    message = str(error)
                self.assertIn(start, message)
                self.assertIn(end, message)
                self.assertIn(requested.strftime("%Y-%m-%d"), message)


class TestGOESDiscovery(unittest.TestCase):
    def test_select_scan_object_signature(self):
        self.assertEqual(
            list(inspect.signature(select_goes_scan_object).parameters),
            ["paths", "platform", "channel", "requested_time"],
        )

    def test_cmipf_prefix(self):
        requested = datetime(2026, 8, 7, 12, 30)
        self.assertEqual(
            goes_cmipf_prefix("GOES-18", requested),
            "noaa-goes18/ABI-L2-CMIPF/2026/219/12/",
        )
        self.assertEqual(
            goes_cmipf_prefix("GOES-19", requested),
            "noaa-goes19/ABI-L2-CMIPF/2026/219/12/",
        )
        with self.assertRaises(ValueError):
            goes_cmipf_prefix("Himawari-9", requested)

    def test_parse_scan_timestamp_uses_two_second_digits_and_one_tenth_digit(self):
        # CMIPF uses YYYYDDDHHMMSSS: the final digit is tenths, not milliseconds.
        path = "OR_ABI-L2-CMIPF-M6C14_G18_s20262191230170_e20262191230599.nc"
        parsed = _parse_goes_scan_object(path)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed[2], datetime(2026, 8, 7, 12, 30, 17, 0))
        self.assertEqual(parsed[3], datetime(2026, 8, 7, 12, 30, 59, 900000))

    def test_parse_scan_object_rejects_invalid_field_length_and_date(self):
        short_path = "OR_ABI-L2-CMIPF-M6C14_G18_s2026219123017_e20262191230599.nc"
        invalid_second_path = "OR_ABI-L2-CMIPF-M6C14_G18_s20262191230999_e20262191230599.nc"
        invalid_date_path = "OR_ABI-L2-CMIPF-M6C14_G18_s20263671230170_e20262191230599.nc"
        self.assertIsNone(_parse_goes_scan_object(short_path))
        for path in (invalid_second_path, invalid_date_path):
            with self.assertRaisesRegex(ValueError, "Invalid GOES timestamp"):
                _parse_goes_scan_object(path)

    def test_select_scan_object_matches_requested_slot_not_exact_seconds(self):
        path = "OR_ABI-L2-CMIPF-M6C14_G18_s20262191230170_e20262191230599.nc"
        self.assertEqual(
            select_goes_scan_object([path], "GOES-18", "C14", datetime(2026, 8, 7, 12, 30)),
            path,
        )
        for requested in (datetime(2026, 8, 7, 12, 30, 17), datetime(2026, 8, 7, 12, 35)):
            with self.assertRaisesRegex(ValueError, "GOES-18.*C14"):
                select_goes_scan_object([path], "GOES-18", "C14", requested)
        with self.assertRaisesRegex(ValueError, "GOES-18.*C14.*2026-08-07 12:40:00"):
            select_goes_scan_object([path], "GOES-18", "C14", datetime(2026, 8, 7, 12, 40))

    def test_select_scan_object_filters_platform_and_chooses_earliest_scan(self):
        goes18_late = "OR_ABI-L2-CMIPF-M6C14_G18_s20262191230300_e20262191230599.nc"
        goes18_early = "OR_ABI-L2-CMIPF-M6C14_G18_s20262191230170_e20262191230599.nc"
        goes19 = "OR_ABI-L2-CMIPF-M6C14_G19_s20262191230170_e20262191230599.nc"
        paths = [goes18_late, goes19, goes18_early]
        requested = datetime(2026, 8, 7, 12, 30)
        self.assertEqual(select_goes_scan_object(paths, "GOES-18", "C14", requested), goes18_early)
        self.assertEqual(select_goes_scan_object(paths, "GOES-19", "C14", requested), goes19)

    def test_select_scan_object_filters_goes_16_and_17_by_matching_satellite(self):
        requested = datetime(2022, 1, 1, 12, 30)
        goes16 = "OR_ABI-L2-CMIPF-M6C14_G16_s20220011230170_e20220011230599.nc"
        goes17 = "OR_ABI-L2-CMIPF-M6C14_G17_s20220011230170_e20220011230599.nc"
        paths = [goes17, goes16]
        self.assertEqual(select_goes_scan_object(paths, "GOES-16", "C14", requested), goes16)
        self.assertEqual(select_goes_scan_object(paths, "GOES-17", "C14", requested), goes17)

    def test_select_scan_object_rejects_wrong_channel(self):
        path = "OR_ABI-L2-CMIPF-M6C14_G18_s20262191230170_e20262191230599.nc"
        with self.assertRaisesRegex(ValueError, "GOES-18.*C13.*2026-08-07 12:30:00"):
            select_goes_scan_object([path], "GOES-18", "C13", datetime(2026, 8, 7, 12, 30))


class FakeVariable:
    def __init__(self, values, attrs=None):
        self.values = np.asarray(values)
        self.attrs = attrs or {}


class FakeDataset:
    def __init__(self, values, attrs=None, x=None, y=None):
        values = np.asarray(values)
        if x is None:
            x = np.arange(values.shape[1]) if values.ndim == 2 else ()
        if y is None:
            y = np.arange(values.shape[0]) if values.ndim == 2 else ()
        self.variables = {
            "CMI": FakeVariable(values),
            "x": FakeVariable(x),
            "y": FakeVariable(y),
            "goes_imager_projection": FakeVariable((), attrs),
        }
        self.closed = False

    def __getitem__(self, key):
        return self.variables[key]

    def close(self):
        self.closed = True


class FailingCloseDataset(FakeDataset):
    def __init__(self, *args, close_error, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_error = close_error

    def close(self):
        self.closed = True
        raise self.close_error


class FakeHandle:
    def __init__(self, path):
        self.path = path
        self.closed = False

    def close(self):
        self.closed = True


class FakeS3:
    def __init__(self, paths):
        self.paths = paths
        self.ls_calls = []
        self.opened = []
        self.handles = []

    def ls(self, prefix):
        self.ls_calls.append(prefix)
        return list(self.paths)

    def open(self, path, mode):
        self.opened.append((path, mode))
        handle = FakeHandle(path)
        self.handles.append(handle)
        return handle


class TestGOESSceneLoader(unittest.TestCase):
    PROJECTION = {
        "perspective_point_height": 35786023.0,
        "longitude_of_projection_origin": -137.2,
        "sweep_angle_axis": "x",
        "semi_major_axis": 6378137.0,
        "semi_minor_axis": 6356752.31414,
    }
    PREFIX = "noaa-goes18/ABI-L2-CMIPF/2026/219/12/"
    C08 = PREFIX + "OR_ABI-L2-CMIPF-M6C08_G18_s20262191230170_e20262191230599.nc"
    C09 = PREFIX + "OR_ABI-L2-CMIPF-M6C09_G18_s20262191230170_e20262191230599.nc"

    def _datasets(self):
        return {"C08": FakeDataset([[270.15]], self.PROJECTION), "C09": FakeDataset([[274.15]], self.PROJECTION)}

    def test_loads_avg_channels_from_exact_prefix_and_closes_handles(self):
        fs = FakeS3([self.C08, self.C09])
        datasets = self._datasets()
        opened = []

        def fake_open_dataset(handle, engine):
            self.assertEqual(engine, "h5netcdf")
            opened.append(handle.path)
            return datasets["C08" if handle.path == self.C08 else "C09"]

        scene = load_goes_scene("GOES-18", datetime(2026, 8, 7, 12, 30), "WV", "AVG", fs=fs, open_dataset=fake_open_dataset)
        self.assertEqual(fs.ls_calls, [self.PREFIX])
        self.assertEqual(opened, [self.C08, self.C09])
        self.assertEqual(scene.source_channels, ("C08", "C09"))
        self.assertEqual(scene.scan_start, datetime(2026, 8, 7, 12, 30, 17))
        self.assertEqual(scene.scan_end, datetime(2026, 8, 7, 12, 30, 59, 900000))
        self.assertTrue(all(handle.closed for handle in fs.handles))

    def test_closes_first_dataset_and_all_handles_when_second_open_fails(self):
        fs = FakeS3([self.C08, self.C09])
        first = FakeDataset([[270.15]], self.PROJECTION)
        calls = 0

        def failing_open_dataset(handle, engine):
            nonlocal calls
            calls += 1
            if calls == 1:
                return first
            raise OSError("broken C09 source")

        with self.assertRaisesRegex(OSError, "broken C09 source"):
            load_goes_scene("GOES-18", datetime(2026, 8, 7, 12, 30), "WV", "AVG", fs=fs, open_dataset=failing_open_dataset)
        self.assertTrue(first.closed)
        self.assertTrue(all(handle.closed for handle in fs.handles))

    def test_rejects_archive_date_before_listing(self):
        fs = FakeS3([])
        with self.assertRaisesRegex(ValueError, "GOES-19.*2025-04-07.*至今.*2024-08-01"):
            load_goes_scene("GOES-19", datetime(2024, 8, 1, 9, 0), "IR", "B14", fs=fs, open_dataset=lambda handle, engine: None)
        self.assertEqual(fs.ls_calls, [])

    def test_rejects_non_slot_before_listing(self):
        fs = FakeS3([self.C08, self.C09])
        for requested in (datetime(2026, 8, 7, 12, 35), datetime(2026, 8, 7, 12, 30, 17)):
            with self.subTest(requested=requested), self.assertRaises(ValueError):
                load_goes_scene("GOES-18", requested, "WV", "AVG", fs=fs, open_dataset=lambda handle, engine: None)
        self.assertEqual(fs.ls_calls, [])

    def test_listing_missing_prefix_reports_generic_scan_error(self):
        class MissingPrefixS3:
            def ls(self, prefix):
                raise FileNotFoundError(prefix)

        with self.assertRaises(ValueError) as raised:
            load_goes_scene(
                "GOES-19", datetime(2025, 4, 7, 9, 0), "IR", "B14",
                fs=MissingPrefixS3(), open_dataset=lambda handle, engine: None,
            )

        message = str(raised.exception)
        self.assertIn("No CMIPF scan", message)
        self.assertIn("GOES-19", message)
        self.assertIn("09:00", message)
        self.assertNotIn("noaa-goes19/", message)
        self.assertNotIn("Traceback", message)
        self.assertIsInstance(raised.exception.__cause__, FileNotFoundError)

    def test_missing_channel_is_reported_before_opening_any_dataset(self):
        fs = FakeS3([self.C08])
        with self.assertRaisesRegex(ValueError, "GOES-18.*C09.*2026-08-07 12:30:00"):
            load_goes_scene("GOES-18", datetime(2026, 8, 7, 12, 30), "WV", "AVG", fs=fs, open_dataset=lambda handle, engine: None)
        self.assertEqual(fs.opened, [])

    def test_single_channel_data_types_open_only_the_mapped_channel(self):
        path = self.PREFIX + "OR_ABI-L2-CMIPF-M6C14_G18_s20262191230170_e20262191230599.nc"
        fs = FakeS3([path])
        dataset = FakeDataset([[273.15]], self.PROJECTION)
        scene = load_goes_scene("GOES-18", datetime(2026, 8, 7, 12, 30), "IR", "B14", fs=fs, open_dataset=lambda handle, engine: dataset)
        self.assertEqual(fs.opened, [(path, "rb")])
        self.assertEqual(scene.source_channels, ("C14",))

    def test_ignores_foreign_prefix_paths_before_opening_expected_scan(self):
        expected = self.PREFIX + "OR_ABI-L2-CMIPF-M6C14_G18_s20262191230170_e20262191230599.nc"
        foreign = "noaa-goes19/ABI-L2-CMIPF/2026/219/12/OR_ABI-L2-CMIPF-M6C14_G18_s20262191230170_e20262191230599.nc"
        fs = FakeS3([foreign, expected])
        dataset = FakeDataset([[273.15]], self.PROJECTION)

        load_goes_scene("GOES-18", datetime(2026, 8, 7, 12, 30), "IR", "B14", fs=fs, open_dataset=lambda handle, engine: dataset)

        self.assertEqual(fs.opened, [(expected, "rb")])

    def test_foreign_prefix_path_does_not_supply_cmipf_scan(self):
        foreign = "noaa-goes19/ABI-L2-CMIPF/2026/219/12/OR_ABI-L2-CMIPF-M6C14_G18_s20262191230170_e20262191230599.nc"
        fs = FakeS3([foreign])

        with self.assertRaisesRegex(ValueError, "No CMIPF scan"):
            load_goes_scene("GOES-18", datetime(2026, 8, 7, 12, 30), "IR", "B14", fs=fs, open_dataset=lambda handle, engine: None)

        self.assertEqual(fs.opened, [])

    def test_avg_scan_times_must_match_before_opening(self):
        second = self.C09.replace("s20262191230170_e20262191230599", "s20262191230200_e20262191230599")
        fs = FakeS3([self.C08, second])
        with self.assertRaisesRegex(ValueError, "scan time"):
            load_goes_scene("GOES-18", datetime(2026, 8, 7, 12, 30), "WV", "AVG", fs=fs, open_dataset=lambda handle, engine: None)
        self.assertEqual(fs.opened, [])


class TestGOESSceneReader(unittest.TestCase):
    PROJECTION = {
        "perspective_point_height": 35786023.0,
        "longitude_of_projection_origin": -137.2,
        "sweep_angle_axis": "x",
        "semi_major_axis": 6378137.0,
        "semi_minor_axis": 6356752.31414,
    }

    def test_ir_b14_converts_to_celsius_and_closes_dataset(self):
        dataset = FakeDataset([[273.15, 274.15]], self.PROJECTION)
        scene = scene_from_goes_datasets(
            "GOES-18", "IR", "B14", {"C14": dataset},
            datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
        )
        np.testing.assert_array_equal(scene.data, [[0.0, 1.0]])
        self.assertEqual(scene.source_channels, ("C14",))
        self.assertEqual(scene.unit_kind, "brightness_temperature")
        self.assertTrue(dataset.closed)

    def test_wv_avg_uses_pixel_median_and_closes_all_on_error(self):
        first = FakeDataset([[270.15, 280.15]], self.PROJECTION)
        second = FakeDataset([[274.15, 276.15]], self.PROJECTION)
        scene = scene_from_goes_datasets(
            "GOES-18", "WV", "AVG", {"C08": first, "C09": second},
            datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
        )
        np.testing.assert_array_equal(scene.data, [[-1.0, 5.0]])
        self.assertEqual(scene.source_channels, ("C08", "C09"))
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)

    def test_vis_b03_converts_abi_c02_reflectance_factor(self):
        dataset = FakeDataset([[0.25]], self.PROJECTION)
        scene = scene_from_goes_datasets(
            "GOES-18", "VIS", "B03", {"C02": dataset},
            datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
        )
        np.testing.assert_array_equal(scene.data, [[25.0]])
        self.assertEqual(scene.unit_kind, "reflectance")
        self.assertTrue(dataset.closed)

    def test_projection_and_coordinates_are_copied(self):
        x = np.array([-0.1, 0.1])
        y = np.array([-0.2])
        dataset = FakeDataset([[273.15, 274.15]], self.PROJECTION, x=x, y=y)
        scene = scene_from_goes_datasets(
            "GOES-18", "IR", "B14", {"C14": dataset},
            datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
        )
        self.assertEqual(scene.projection, ProjectionMetadata(**self.PROJECTION))
        self.assertIsNot(scene.x_scan_rad, x)
        self.assertIsNot(scene.y_scan_rad, y)
        np.testing.assert_array_equal(scene.x_scan_rad, x)
        np.testing.assert_array_equal(scene.y_scan_rad, y)

    def test_rejects_invalid_coordinate_dimensions_and_cmi_shape(self):
        cases = [
            (FakeDataset([[273.15]], self.PROJECTION, x=[[0.0]], y=[0.0]), "x.*one-dimensional"),
            (FakeDataset([[273.15]], self.PROJECTION, x=[0.0], y=[[0.0]]), "y.*one-dimensional"),
            (FakeDataset([[273.15, 274.15]], self.PROJECTION, x=[0.0], y=[0.0]), "C14.*actual.*expected"),
        ]
        for dataset, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    scene_from_goes_datasets(
                        "GOES-18", "IR", "B14", {"C14": dataset},
                        datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
                    )
                self.assertTrue(dataset.closed)

    def test_avg_requires_matching_data_coordinates_and_projection(self):
        cases = [
            (FakeDataset([[273.15, 274.15]], self.PROJECTION), FakeDataset([[275.15]], self.PROJECTION), "C09.*actual.*expected"),
            (FakeDataset([[273.15]], self.PROJECTION, x=[0.0], y=[0.0]), FakeDataset([[275.15]], self.PROJECTION, x=[0.1], y=[0.0]), "C09.*x"),
            (FakeDataset([[273.15]], self.PROJECTION, x=[0.0], y=[0.0]), FakeDataset([[275.15]], {**self.PROJECTION, "semi_major_axis": 1.0}, x=[0.0], y=[0.0]), "C09.*semi_major_axis"),
        ]
        for first, second, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    scene_from_goes_datasets(
                        "GOES-18", "WV", "AVG", {"C08": first, "C09": second},
                        datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
                    )
                self.assertTrue(first.closed)
                self.assertTrue(second.closed)

    def test_projection_attributes_are_converted_and_invalid_values_are_clear(self):
        attrs = {field: str(value) for field, value in self.PROJECTION.items()}
        dataset = FakeDataset([[273.15]], attrs, x=[0.0], y=[0.0])
        scene = scene_from_goes_datasets(
            "GOES-18", "IR", "B14", {"C14": dataset},
            datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
        )
        self.assertEqual(scene.projection, ProjectionMetadata(**self.PROJECTION))

        invalid = FakeDataset([[273.15]], {**self.PROJECTION, "semi_major_axis": "bad"}, x=[0.0], y=[0.0])
        with self.assertRaisesRegex(ValueError, "semi_major_axis"):
            scene_from_goes_datasets(
                "GOES-18", "IR", "B14", {"C14": invalid},
                datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
            )
        self.assertTrue(invalid.closed)

    def test_close_errors_do_not_mask_processing_errors_and_close_all_datasets(self):
        first = FailingCloseDataset([[273.15]], self.PROJECTION, close_error=OSError("first"))
        second = FailingCloseDataset([274.15], self.PROJECTION, close_error=OSError("second"))
        with self.assertRaisesRegex(ValueError, "actual.*expected"):
            scene_from_goes_datasets(
                "GOES-18", "WV", "AVG", {"C08": first, "C09": second},
                datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
            )
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)

    def test_close_errors_raise_runtime_error_after_successful_processing(self):
        first = FailingCloseDataset([[273.15]], self.PROJECTION, close_error=OSError("first"))
        second = FailingCloseDataset([[274.15]], self.PROJECTION, close_error=OSError("second"))
        with self.assertRaisesRegex(ValueError, "Failed to close GOES dataset.*C08.*C09"):
            scene_from_goes_datasets(
                "GOES-18", "WV", "AVG", {"C08": first, "C09": second},
                datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
            )
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)

    def test_invalid_dataset_inputs_raise_clear_value_error_and_close(self):
        cases = [
            ("IR", "B14", {"C14": FakeDataset([273.15], self.PROJECTION)}, "C14.*actual.*expected"),
            ("IR", "B14", {"C14": FakeDataset([[273.15]], {})}, "projection"),
            ("IR", "B13", {"C14": FakeDataset([[273.15]], self.PROJECTION)}, "required channel"),
        ]
        for data_type, band, datasets, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    scene_from_goes_datasets(
                        "GOES-18", data_type, band, datasets,
                        datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
                    )
                for dataset in datasets.values():
                    self.assertTrue(dataset.closed)

    def test_closes_all_datasets_when_processing_raises(self):
        first = FakeDataset([[273.15]], self.PROJECTION)
        second = FakeDataset([274.15], self.PROJECTION)
        with self.assertRaisesRegex(ValueError, "actual.*expected"):
            scene_from_goes_datasets(
                "GOES-18", "WV", "AVG", {"C08": first, "C09": second},
                datetime(2026, 8, 7, 12, 0), datetime(2026, 8, 7, 12, 10),
            )
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)


class TestScene(unittest.TestCase):
    def test_dataclass_field_contracts_are_complete_and_ordered(self):
        self.assertEqual(
            [field.name for field in fields(ProjectionMetadata)],
            [
                "perspective_point_height",
                "longitude_of_projection_origin",
                "sweep_angle_axis",
                "semi_major_axis",
                "semi_minor_axis",
            ],
        )
        self.assertEqual(
            [field.name for field in fields(Scene)],
            [
                "data",
                "x_scan_rad",
                "y_scan_rad",
                "projection",
                "platform",
                "logical_band",
                "source_channels",
                "unit_kind",
                "scan_start",
                "scan_end",
                "region",
            ],
        )

    def test_scene_and_projection_are_frozen(self):
        projection = ProjectionMetadata(
            perspective_point_height=35786023.0,
            longitude_of_projection_origin=-137.2,
            sweep_angle_axis="x",
            semi_major_axis=6378137.0,
            semi_minor_axis=6356752.31414,
        )
        scene = Scene(
            data=np.array([[1.0]]),
            x_scan_rad=np.array([0.0]),
            y_scan_rad=np.array([0.0]),
            projection=projection,
            platform="GOES-18",
            logical_band="B14",
            source_channels=("C14",),
            unit_kind="brightness_temperature",
            scan_start=datetime(2026, 8, 7, 12, 0),
            scan_end=datetime(2026, 8, 7, 12, 10),
            region="F",
        )
        with self.assertRaises(FrozenInstanceError):
            scene.platform = "GOES-19"
        with self.assertRaises(FrozenInstanceError):
            projection.sweep_angle_axis = "y"

    def test_scene_retains_all_values(self):
        data = np.array([[1.0, 2.0]])
        x_scan_rad = np.array([-0.01, 0.02])
        y_scan_rad = np.array([0.03])
        projection = ProjectionMetadata(
            perspective_point_height=35786023.0,
            longitude_of_projection_origin=-137.2,
            sweep_angle_axis="x",
            semi_major_axis=6378137.0,
            semi_minor_axis=6356752.31414,
        )
        scan_start = datetime(2026, 8, 7, 12, 0)
        scan_end = datetime(2026, 8, 7, 12, 10)
        scene = Scene(
            data=data,
            x_scan_rad=x_scan_rad,
            y_scan_rad=y_scan_rad,
            projection=projection,
            platform="GOES-18",
            logical_band="B14",
            source_channels=("C14", "C15"),
            unit_kind="brightness_temperature",
            scan_start=scan_start,
            scan_end=scan_end,
            region="F",
        )
        np.testing.assert_array_equal(scene.data, data)
        np.testing.assert_array_equal(scene.x_scan_rad, x_scan_rad)
        np.testing.assert_array_equal(scene.y_scan_rad, y_scan_rad)
        self.assertEqual(scene.projection, projection)
        self.assertEqual(scene.projection.perspective_point_height, 35786023.0)
        self.assertEqual(scene.projection.longitude_of_projection_origin, -137.2)
        self.assertEqual(scene.projection.sweep_angle_axis, "x")
        self.assertEqual(scene.projection.semi_major_axis, 6378137.0)
        self.assertEqual(scene.projection.semi_minor_axis, 6356752.31414)
        self.assertEqual(scene.platform, "GOES-18")
        self.assertEqual(scene.logical_band, "B14")
        self.assertEqual(scene.source_channels, ("C14", "C15"))
        self.assertEqual(scene.unit_kind, "brightness_temperature")
        self.assertEqual(scene.scan_start, scan_start)
        self.assertEqual(scene.scan_end, scan_end)
        self.assertEqual(scene.region, "F")


if __name__ == "__main__":
    unittest.main()

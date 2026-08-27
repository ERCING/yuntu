import math
import unittest

import numpy as np

import cartopy.crs as ccrs
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from himawari_ir_toolkit.draw_ir_fulldisk import (
    compute_target_lonlat_bounds,
    draw_target_graticule_and_labels,
    get_decoration_subplot_adjustments,
    get_decoration_layout_metrics,
    _pick_nearest_point_index,
    _split_valid_segments,
    downsample_for_render,
    get_render_stride,
)


class TestTargetGraticuleHelpers(unittest.TestCase):
    def test_downsample_for_render_limits_large_vis_arrays(self):
        data = np.arange(2200 * 2200, dtype=np.float32).reshape(2200, 2200)

        rendered = downsample_for_render(data, max_dimension=409)

        self.assertLessEqual(max(rendered.shape), 409)
        self.assertEqual(rendered.dtype, np.float32)

    def test_get_render_stride_limits_vis_to_11000_pixels(self):
        self.assertEqual(get_render_stride((22000, 22000)), 2)

    def test_split_valid_segments_splits_on_invalid(self):
        x = np.array([0, 1, math.nan, 3, 4, math.nan, 6], dtype=float)
        y = np.array([0, 1, math.nan, 3, 4, math.nan, 6], dtype=float)
        segs = _split_valid_segments(x, y)
        self.assertEqual(len(segs), 3)
        self.assertTrue(np.allclose(segs[0][0], [0, 1]))
        self.assertTrue(np.allclose(segs[1][0], [3, 4]))
        self.assertTrue(np.allclose(segs[2][0], [6]))

    def test_pick_nearest_point_index_works(self):
        x = np.array([0, 2, 5, 9], dtype=float)
        idx = _pick_nearest_point_index(x, target=6.1)
        self.assertEqual(idx, 2)


class TestTargetGraticuleCartopy(unittest.TestCase):
    def test_compute_target_lonlat_bounds_returns_reasonable_values(self):
        geos = ccrs.Geostationary(
            central_longitude=175.0,
            satellite_height=35785863.0,
            sweep_axis="x",
        )
        extent = (-1_000_000.0, 1_000_000.0, -1_000_000.0, 1_000_000.0)
        b = compute_target_lonlat_bounds(geos, extent, samples=200)
        self.assertIsNotNone(b)
        lon_min, lon_max, lat_min, lat_max = b
        self.assertTrue(np.isfinite(lon_min))
        self.assertTrue(np.isfinite(lon_max))
        self.assertTrue(-90.0 <= lat_min <= 90.0)
        self.assertTrue(-90.0 <= lat_max <= 90.0)
        self.assertTrue(lon_min < lon_max)
        self.assertTrue(lat_min < lat_max)
        self.assertLess(lon_max - lon_min, 120.0)

    def test_draw_target_graticule_and_labels_does_not_crash(self):
        geos = ccrs.Geostationary(
            central_longitude=175.0,
            satellite_height=35785863.0,
            sweep_axis="x",
        )
        extent = (-1_000_000.0, 1_000_000.0, -1_000_000.0, 1_000_000.0)
        fig = plt.figure(figsize=(4, 4), dpi=80)
        ax = fig.add_subplot(1, 1, 1, projection=geos)
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        draw_target_graticule_and_labels(ax, geos, extent, step_deg=1.0, npts=60)
        self.assertGreaterEqual(len(ax.lines), 1)
        self.assertGreaterEqual(len(ax.texts), 1)
        plt.close(fig)


class TestDecorationLayoutMetrics(unittest.TestCase):
    def test_layout_metrics_follow_pixel_targets_for_large_figure(self):
        m = get_decoration_layout_metrics(region_full="FLDK", fig_w=36.7, fig_h=36.7, dpi=150)
        self.assertEqual(m["info_fontsize"], 35)
        self.assertEqual(m["cbar_tick_size"], 35)
        self.assertAlmostEqual(m["header_gap_fig"], 22 / (36.7 * 150), places=6)
        self.assertAlmostEqual(m["cbar_gap"], 10 / (36.7 * 150), places=6)
        self.assertGreaterEqual(m["cbar_width"], 0.018)

    def test_layout_metrics_clamp_small_figure_sizes(self):
        m = get_decoration_layout_metrics(region_full="Target", fig_w=3.45, fig_h=3.33, dpi=150)
        self.assertLessEqual(m["info_fontsize"], 7)
        self.assertLessEqual(m["cbar_tick_size"], 6)
        self.assertGreaterEqual(m["cbar_width"], 0.010)


class TestDecorationSubplotAdjustments(unittest.TestCase):
    def test_fldk_decorated_layout_reduces_whitespace(self):
        adj = get_decoration_subplot_adjustments(region_full="FLDK", add_decorations=True)
        self.assertEqual(adj["left"], 0.01)
        self.assertEqual(adj["right"], 0.945)
        self.assertEqual(adj["top"], 0.975)
        self.assertEqual(adj["bottom"], 0.01)

    def test_target_decorated_layout_stays_conservative(self):
        adj = get_decoration_subplot_adjustments(region_full="Target", add_decorations=True)
        self.assertEqual(adj["left"], 0.04)
        self.assertEqual(adj["right"], 0.905)
        self.assertEqual(adj["top"], 0.935)
        self.assertEqual(adj["bottom"], 0.035)


if __name__ == "__main__":
    unittest.main()

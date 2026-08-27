from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
REQUIRED_PACKAGES = {
    "numpy",
    "pandas",
    "matplotlib",
    "cartopy",
    "Pillow",
    "pycontrails",
    "xarray",
    "s3fs",
    "h5netcdf",
    "h5py",
    "pyinstaller",
}
REQUIRED_COLLECTS = {
    "cartopy",
    "matplotlib",
    "PIL",
    "xarray",
    "s3fs",
    "fsspec",
    "aiohttp",
    "h5netcdf",
    "h5py",
}


class TestPackagingConfiguration(unittest.TestCase):
    def test_requirements_cover_runtime_packages(self):
        lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        package_names = {line.split("[", 1)[0].split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].strip() for line in lines if line.strip() and not line.startswith("#")}
        self.assertTrue(REQUIRED_PACKAGES <= package_names)

    def test_spec_collects_dynamic_goes_dependencies(self):
        spec = (ROOT / "build" / "HimawariIRToolkit.spec").read_text(encoding="utf-8")
        for package in REQUIRED_COLLECTS:
            self.assertIn(f"collect_all('{package}')", spec)


if __name__ == "__main__":
    unittest.main()

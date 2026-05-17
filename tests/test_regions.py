"""Tests for domain/regions.py: loader, validation, model."""
import pytest

from app.domain.regions import SailingRegion, SailingZone, load_regions


class TestLoadRegions:
    def test_loads_fixture_yaml(self, sailing_areas_yaml):
        regions = load_regions(sailing_areas_yaml)
        assert len(regions) == 1
        assert regions[0].id == "test-bay"

    def test_loads_real_yaml(self, tmp_path):
        from pathlib import Path
        real = Path(__file__).parent.parent / "data" / "sailing_areas.yaml"
        regions = load_regions(real)
        assert len(regions) == 3
        ids = [r.id for r in regions]
        assert "sf-bay" in ids
        assert "puget-sound" in ids
        assert "sardinia" in ids

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_regions(tmp_path / "nonexistent.yaml") == []

    def test_default_zone(self, sailing_areas_yaml):
        region = load_regions(sailing_areas_yaml)[0]
        assert region.default_zone.id == "test-zone"

    def test_noaa_flags(self, sailing_areas_yaml):
        region = load_regions(sailing_areas_yaml)[0]
        assert region.has_noaa_tides() is True
        assert region.has_noaa_warnings() is True

    def test_sardinia_no_noaa(self, tmp_path):
        from pathlib import Path
        real = Path(__file__).parent.parent / "data" / "sailing_areas.yaml"
        regions = load_regions(real)
        sardinia = next(r for r in regions if r.id == "sardinia")
        assert sardinia.has_noaa_tides() is False
        assert sardinia.has_noaa_warnings() is False

    def test_duplicate_region_id_raises(self, tmp_path):
        yaml_text = """
- id: dup
  name: A
  country: US
  timezone: UTC
  zones:
    - {id: z1, name: Z1, latitude: 37.0, longitude: -122.0, exposure: open, hazards: []}
- id: dup
  name: B
  country: US
  timezone: UTC
  zones:
    - {id: z2, name: Z2, latitude: 38.0, longitude: -121.0, exposure: open, hazards: []}
"""
        p = tmp_path / "dup.yaml"
        p.write_text(yaml_text)
        with pytest.raises(ValueError, match="duplicate region id"):
            load_regions(p)

    def test_missing_id_raises(self, tmp_path):
        yaml_text = """
- name: No ID
  country: US
  timezone: UTC
  zones:
    - {id: z1, name: Z1, latitude: 37.0, longitude: -122.0, exposure: open, hazards: []}
"""
        p = tmp_path / "noid.yaml"
        p.write_text(yaml_text)
        with pytest.raises(ValueError, match="missing required field"):
            load_regions(p)


class TestSailingZone:
    def test_invalid_latitude_raises(self):
        with pytest.raises(ValueError):
            SailingZone(id="z", name="Z", latitude=91.0, longitude=0.0, exposure="open", hazards=[])

    def test_invalid_longitude_raises(self):
        with pytest.raises(ValueError):
            SailingZone(id="z", name="Z", latitude=0.0, longitude=181.0, exposure="open", hazards=[])

    def test_invalid_exposure_raises(self):
        with pytest.raises(ValueError):
            SailingZone(id="z", name="Z", latitude=0.0, longitude=0.0, exposure="unknown", hazards=[])

    def test_valid_zone(self):
        z = SailingZone(
            id="cf", name="City Front", latitude=37.808, longitude=-122.435,
            exposure="open", hazards=["fog", "shipping"],
        )
        assert z.id == "cf"
        assert len(z.hazards) == 2

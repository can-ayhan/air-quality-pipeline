from airquality.config import load_coverage


def test_coverage_file_lists_cities_and_pollutants():
    coverage = load_coverage()
    assert [c.name for c in coverage.cities][:2] == ["Warszawa", "Kraków"]
    assert len(coverage.cities) == 7
    assert "PM2.5" in coverage.pollutants and "NOx" not in coverage.pollutants


def test_every_city_has_a_point_inside_poland():
    for city in load_coverage().cities:
        assert 49.0 < city.latitude < 55.0, city
        assert 14.0 < city.longitude < 24.2, city

import matplotlib

matplotlib.use("Agg")

import pandas as pd

from pages.analyze_impacts import plot_single_year, plot_yearly_comparison

SMALL_GROUP_NOTE = "fewer than 2 locations"
YEARS = [2020, 2021]  # multi-year needs at least two years


def _frame(locations_per_group, years):
    rows = []
    for status in ("Dam", "Non-dam"):
        for loc in range(locations_per_group):
            for year in years:
                for month in (6, 7):
                    rows.append(
                        {
                            "id_property": f"{status}{loc}",
                            "Dam_status": status,
                            "Image_month": month,
                            "analysis_year": year,
                            "NDVI": 0.5 + loc / 10,
                            "NDWI_Green": -0.1,
                            "LST": 20.0 + loc,
                            "ET": 80.0 + loc,
                        }
                    )
    return pd.DataFrame(rows)


def _footer(fig):
    return " ".join(t.get_text() for t in fig.texts)


def test_single_dam_figures_note_missing_error_bars():
    assert SMALL_GROUP_NOTE in _footer(plot_single_year(_frame(1, [2020])))
    assert SMALL_GROUP_NOTE in _footer(plot_yearly_comparison(_frame(1, YEARS), YEARS, [6, 7]))


def test_no_note_when_every_group_has_two_locations():
    assert SMALL_GROUP_NOTE not in _footer(plot_single_year(_frame(2, [2020])))
    assert SMALL_GROUP_NOTE not in _footer(plot_yearly_comparison(_frame(2, YEARS), YEARS, [6, 7]))

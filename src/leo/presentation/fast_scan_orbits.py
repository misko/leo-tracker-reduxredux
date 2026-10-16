"""Four standard PNGs from already calibrated, associated orbit lanes."""

from io import BytesIO

from leo.contracts.fast_scan_orbits import PLOT_NAMES
from leo.presentation.orbit_plot import make_orbit_plot


def render_fast_scan_orbits(lanes, *, title, alias_period_hz, subtitle=""):
    products = {}
    for name in PLOT_NAMES:
        low, high = (1, 4) if name.startswith("ch1-4") else (5, 8)
        selected = tuple(lane for lane in lanes if low <= int(lane.channel[2:]) <= high)
        figure = make_orbit_plot(
            selected,
            title=f"{title} · CH{low}–{high}",
            alias_period_hz=alias_period_hz,
            time_limits_s=(0, 300),
            observation_label="top-one passing GLRT windows",
            subtitle=subtitle,
            panel="unassociated" if name.endswith("unassociated") else "all",
        )
        stream = BytesIO()
        figure.savefig(stream, format="png")
        figure.clear()
        products[name] = stream.getvalue()
    return products

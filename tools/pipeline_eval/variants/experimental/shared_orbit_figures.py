"""Render both standard observation views from each constructed orbit figure."""

from io import BytesIO

from leo.contracts.fast_scan_orbits import PLOT_NAMES
from leo.presentation.orbit_plot import make_orbit_plot


def png(figure):
    stream = BytesIO()
    figure.savefig(stream, format="png")
    return stream.getvalue()


def render_shared(lanes, *, title, alias_period_hz, subtitle=""):
    products = {}
    for low, high in ((1, 4), (5, 8)):
        selected = tuple(lane for lane in lanes if low <= int(lane.channel[2:]) <= high)
        figure = make_orbit_plot(selected, title=f"{title} · CH{low}–{high}",
                                 alias_period_hz=alias_period_hz, time_limits_s=(0, 300),
                                 observation_label="top-one passing GLRT windows",
                                 subtitle=subtitle, panel="all")
        try:
            prefix = f"ch{low}-{high}"
            products[prefix+"-all"] = png(figure)
            for axis, lane in zip(figure.axes, selected, strict=True):
                # make_orbit_plot draws the loose observation layer first, then
                # one collection per associated satellite. Orbit tracks are lines.
                loose = sum(p.satellite_id is None for p in lane.peaks)
                satellites = {p.satellite_id for p in lane.peaks if p.satellite_id is not None}
                if len(axis.collections) != 1 + len(satellites):
                    raise ValueError("Unexpected observation-layer layout")
                for collection in axis.collections[1:]:
                    collection.set_visible(False)
                axis.title.set_text(f"{lane.receiver} · {lane.channel} · unassociated only: {loose:,}/{len(lane.peaks):,}")
            figure.texts[-1].set_text("Selected satellite orbit predictions + unassociated GLRT only."
                                      " Colors denote satellite IDs; no alias copies or refitting.")
            products[prefix+"-unassociated"] = png(figure)
        finally:
            figure.clear()
    return {name: products[name] for name in PLOT_NAMES}

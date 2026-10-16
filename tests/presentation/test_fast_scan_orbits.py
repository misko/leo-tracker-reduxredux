from leo.presentation.fast_scan_orbits import PLOT_NAMES, render_fast_scan_orbits
from leo.presentation.orbit_plot import OrbitCurve, OrbitLane, OrbitPeak, make_orbit_plot


def test_separate_panels_preserve_orbits_empty_lanes_and_full_capture_limits():
    curve = OrbitCurve("123", (0, 150, 300), (90, -90, 10))
    lanes = (
        OrbitLane(
            "RX1", "CH1", (OrbitPeak("used", 12, 5, "123"), OrbitPeak("loose", 30, 8)), (curve,)
        ),
        OrbitLane("RX2", "CH1", (), (curve,)),
    )
    for panel, counts in (("all", [1, 1]), ("unassociated", [1])):
        figure = make_orbit_plot(
            lanes, title="Test", panel=panel, alias_period_hz=200, time_limits_s=(0, 300)
        )
        assert len(figure.axes) == 2
        for axis in figure.axes:
            assert axis.get_xlim() == (0, 300)
            assert len(axis.lines) == 1
            assert axis.get_yticklabels()
        assert [len(c.get_offsets()) for c in figure.axes[0].collections] == counts
        assert sum(len(c.get_offsets()) for c in figure.axes[1].collections) == 0
        figure.clear()


def test_four_standard_pngs_include_empty_channels(monkeypatch):
    import leo.presentation.fast_scan_orbits as plots

    original = plots.make_orbit_plot
    calls = []

    def record(lanes, **kwargs):
        calls.append((tuple(lane.channel for lane in lanes), kwargs))
        return original(lanes, **kwargs)

    monkeypatch.setattr(plots, "make_orbit_plot", record)
    lanes = tuple(OrbitLane("RX1", f"CH{channel}", ()) for channel in range(1, 9))
    pngs = render_fast_scan_orbits(lanes, title="Capture", alias_period_hz=200)
    assert tuple(pngs) == PLOT_NAMES
    assert all(data.startswith(b"\x89PNG\r\n\x1a\n") for data in pngs.values())
    assert [c[0] for c in calls] == [("CH1", "CH2", "CH3", "CH4"), ("CH5", "CH6", "CH7", "CH8")] * 2
    assert all(c[1]["time_limits_s"] == (0, 300) for c in calls)

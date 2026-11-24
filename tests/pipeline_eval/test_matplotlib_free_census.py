from reports.ALGO08.v3.matplotlib_free_census import budget, ownership


def clocks(ns):
    return dict(cpu_ns=ns, elapsed_ns=ns)


def module(index, name, parent, ns, phase="active_prefix"):
    return dict(index=index, name=name, parent=parent, phase=phase, exclusive_cpu_ns=ns, exclusive_elapsed_ns=ns)


def test_overlapping_import_roots_use_each_exclusive_interval_once():
    rows = [
        module(0, "tools.algo08_position", None, 1),
        module(1, "leo.presentation.orbit_plot", 0, 10),
        module(2, "matplotlib", 1, 50),
        module(3, "matplotlib.figure", 2, 20),
        module(4, "PIL", 3, 8),
        module(5, "scipy", 0, 80),
    ]
    measured = ownership(rows, ("leo.presentation.orbit_plot", "matplotlib"))
    assert measured["exclusive"] == clocks(80)
    assert measured["inclusive_union"] == clocks(88)


def test_budget_keeps_native_rgba_encoders_and_never_double_counts_render_imports():
    rows = [module(0, "matplotlib", None, 120), module(1, "matplotlib.patches", None, 5, "render")]
    bundle = {"timings": {name: [clocks(ns)] for name, ns in (
        ("all", 600), ("orbits", 300), ("residual_paint", 40), ("residual_scene", 5),
        ("position", 120), ("track-rms", 45))}, "encodes": [clocks(10)] * 8}
    state = budget(rows, bundle, 300e-9)
    assert state["pre_render_matplotlib"]["exclusive"] == clocks(120)
    assert state["ceilings"]["cpu_ns"] == dict(all_figure_ns=600,
        retained_native_and_encode_ns=385, final_two_net_of_encode_ns=145, other_figure_headroom_ns=70,
        gross_removable_ns=335, remaining_target_ns=300, optimism_margin_ns=35)

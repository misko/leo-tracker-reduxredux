from reports.ALGO08.v3.ds30_0359_cairo_score import image_match, speed
from reports.ALGO08.v3.ds30_0359_cairo_visual import artist_check, scene_view


def test_publication_cost_keeps_export_paid_and_the_gap_signed():
    def elapsed(value):
        return {metric: value for metric in ("cpu_s", "elapsed_s")}

    result = speed(dict(installed=elapsed(32), ordinary=elapsed(17), candidate=elapsed(16.5)),
                   elapsed(0.25), elapsed(0.125))
    assert result["elapsed_s"]["remaining_to_half"] == 0.5
    assert result["elapsed_s"]["candidate_with_setup"] == 16.75
    assert result["elapsed_s"]["scene_export"] == 0.125


def test_encoded_rgba_and_shape_checked_independently():
    ordinary = {"orbit": dict(sha256="encoded", rgba_sha256="rgba", size=[2400, 3000])}
    current = {"orbit": dict(sha256="new", rgba_sha256="rgba", size=(2400, 3000))}
    assert image_match(ordinary, current) == {"orbit": dict(sha256=False, rgba_sha256=True, size=True)}


def test_orbit_views_keep_curves_and_bind_their_own_titles_and_visible_peaks():
    plot = dict(footers=("all", "loose"), rows=[dict(titles=("all", "loose"), associated=[1], loose=[2], curves=[3])])
    both, gray = (scene_view(plot, index) for index in range(2))
    assert (both["footers"], gray["footers"]) == (("all",), ("loose",))
    assert gray["rows"] == [dict(titles=("loose",), associated=[], loose=[2], curves=[3])]
    assert both["rows"][0]["associated"] == [1]
    sheet = dict(heading="real", footer="loose", legend=["one"], axes=["lane"], ticks=["interval"])
    assert artist_check(sheet, dict(sheet, heading="wrong")) == dict(heading=False, footer=True, legend=True, axes=True, ticks=True)

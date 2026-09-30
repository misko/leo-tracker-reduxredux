from serialized_layout_figure import layout


def test_serialized_layouts_are_contiguous_and_preserve_optional_displacement():
    for e, t, expected in ((0, 0, 64), (0, 1, 144), (1, 0, 416), (1, 1, 496)):
        fields = layout(e, t)
        end = 0
        for f in fields:
            assert f["start"] == end
            end += f["width"]
        assert end == expected
    starts = [next(f["start"] for f in layout(e, 1)
                   if f["name"] == "Timing + empty options") for e in (0, 1)]
    assert starts[1] - starts[0] == 352

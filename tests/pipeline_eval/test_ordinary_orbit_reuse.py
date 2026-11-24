from types import SimpleNamespace

from reports.ALGO08.v3.ordinary_orbit_reuse import RestoreAfterCopy


class Canvas:
    def __init__(self):
        self.figure = SimpleNamespace(bbox=object())
        self.renderer = object()

    def get_renderer(self):
        return self.renderer


def test_only_the_first_identical_full_region_restore_can_be_elided():
    canvas, other_canvas, region = Canvas(), Canvas(), object()
    copies = RestoreAfterCopy()
    copies.copied(canvas, canvas.figure.bbox, region)
    assert not copies.redundant(other_canvas, region)
    assert copies.redundant(canvas, region)
    assert not copies.redundant(canvas, region)


def test_renderer_or_region_changes_make_the_restore_necessary():
    canvas, region = Canvas(), object()
    copies = RestoreAfterCopy()
    copies.copied(canvas, canvas.figure.bbox, region)
    canvas.renderer = object()
    assert not copies.redundant(canvas, region)
    copies.copied(canvas, canvas.figure.bbox, region)
    assert not copies.redundant(canvas, object())
    copies.copied(canvas, canvas.figure.bbox, region)
    copies.copied(canvas, object(), region)
    assert not copies.redundant(canvas, region)

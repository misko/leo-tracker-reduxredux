from pathlib import Path

import pytest

from reports.ALGO08.v3 import directed_second_enrollment as check


def test_distinct_stages_do_not_union_member_counts_or_accept_other_segments():
    a, b = "/tmp/a/capture-lower-segment-00000000", "/dev/shm/b/capture-lower-segment-00000000"
    rows = [
        f"{a}/iq-000000.ci16.zst\t7",
        f"{b}/iq-000001.ci16.zst\t9",
        f"{a}/iq-000002.ci16.zst\t0",
        "/dev/shm/b/capture-lower-segment-00000001/iq-000003.ci16.zst\t8",
    ]
    assert check.staged_names("\n".join(rows),{"capture-lower":"record"}) == {
        "record": {a: {"iq-000000.ci16.zst":7},b: {"iq-000001.ci16.zst":9}},
    }
    with pytest.raises(ValueError,match="local RAM roots"):
        check.staged_names("/srv/bulk/a/iq-000000.ci16.zst\t7",{})
    with pytest.raises(ValueError,match="Duplicate"):
        check.staged_names("\n".join([rows[0],rows[0]]),{"capture-lower":"record"})


def test_exact_nominal_extent_requires_all_typed_index_and_original_payload_names():
    name = "capture-lower"
    segment = Path(name+"-segment-00000000")
    def row(kind, leaf):
        relative = segment/leaf
        return dict(kind=kind,relative=str(relative),target=str(Path("recording")/name/relative),
                    sha256="sha256:"+"0"*64,size=10)
    rows = [row("manifest","manifest.json"),
            *(row("payload",leaf) for leaf in check.FIRST_SIX),*(row("index",leaf) for leaf in check.INDEXES)]
    book = dict(expected=dict(recording="/original/"+name),files=rows)
    result = check.first_six_book(book)
    assert result["counts"] == {"manifest":1,"payload":6,"index":6}
    assert result["total_bytes"] == 130
    with pytest.raises(ValueError,match="all six"):
        check.first_six_book(dict(book,files=rows[:-1]))
    with pytest.raises(ValueError,match="duplicate"):
        check.first_six_book(dict(book,files=rows+[rows[-1]]))

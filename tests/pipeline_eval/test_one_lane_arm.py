import subprocess
from copy import deepcopy

from tools.pipeline_eval.__main__ import ROOT
from tools.pipeline_eval.qualification import one_lane_arm as run
from tools.pipeline_eval.qualification.one_lane_arm_results import verify_mapping
from tools.pipeline_eval.variants.one_lane_strided import dwell


def test_rf_alternation_ignores_invalid_capture_and_clock_values():
    def item(idx, rf):
        return dict(
            visit=idx,
            status="processed" if rf else "invalid_capture",
            clock=idx * 139 + 18,
            probes=[dict(receiver_id=lane, actual_rf_hz=rf) for lane in (0, 1)] if rf else [],
        )

    rows = [item(i, f) for i, f in enumerate((9, 10, None, 9, 10, 10, 9))]
    assert [lane for _, _, lane, _ in run.annotated(rows, rows)] == [0, 0, 1, 1, 0, 0]
    assert [lane for _, _, lane, _ in run.annotated(rows[3:], rows[3:])] == [0, 0, 1, 1]


def test_rx1_remap_empty_partner_and_native_diagnostic_clocks():
    blank = dict(
        receiver_id=0, probe_index=4, probe_start_ms=20, candidates=[], proposal_executed=0
    )
    kept = dict(blank, receiver_id=1, candidates=[{"score": 4}])
    original = dict(native_rows=2, rows=[dict(blank, candidates=[{"unseen": True}]), kept])
    one = dict(native_rows=1, rows=[blank, dict(kept, timings_ms={"coarse": 3.4})])
    assert all(verify_mapping(original, one, 1).values())
    bad = deepcopy(one)
    bad["rows"][0]["probe_start_ms"] += 1
    assert verify_mapping(original, bad, 1) == dict(active_exact=True, blank=True, clock=False)
    bad["rows"][1]["candidates"] = []
    assert not verify_mapping(original, bad, 1)["active_exact"]


def test_strided_fp64_and_prepared_prefix_equal_packed_both_physical_lanes(tmp_path):
    header = tmp_path / "dwell_input.h"
    header.write_text(dwell((ROOT / f"native/adaptive/detector/{run.DWELL}").read_text()))
    body = tmp_path / "test.c"
    body.write_text(r"""
#include <assert.h>
#include <string.h>
#include "dwell_input.h"
int main(void)
{
    enum { N=2001 };
    int16_t in[4*N], copy[2*N];
    leo_dwell_input packed={0}, strided={0};
    for (int i=0; i<4*N; ++i) in[i]=(int16_t)((i*859%65536)-32768);
    for (int rx=0; rx<2; ++rx) {
        for (int k=0; k<N; ++k) {
            copy[2*k]=in[4*k+2*rx]; copy[2*k+1]=in[4*k+2*rx+1];
        }
        assert(!leo_dwell_input_prepare_single_reuse(&packed,copy,N));
        assert(!leo_dwell_input_prepare_one_strided(&strided,in+2*rx,N));
        assert(!strided.raw[1] && !strided.normalized[1] && !strided.prefix[1]);
        assert(!memcmp(packed.raw[0],strided.raw[0],N*sizeof(*packed.raw[0])));
        assert(!memcmp(packed.normalized[0],strided.normalized[0],2*N*sizeof(float)));
        assert(!memcmp(packed.prefix[0],strided.prefix[0],(N+1)*sizeof(double)));
    }
    leo_dwell_input_free(&packed);
    leo_dwell_input_free(&strided);
}
""")
    target = tmp_path / "test"
    subprocess.run(
        ["cc", "-std=c11", "-O3", "-ffp-contract=off", str(body), "-o", str(target)], check=True
    )
    subprocess.run([str(target)], check=True)

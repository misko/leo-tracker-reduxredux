"""Measure stock fractional score recovery while the queried lane remains loaded."""

import ctypes as ct
import json
import sys
from collections import Counter, defaultdict
from contextlib import ExitStack
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental import receiver_phase_free_overlay as overlay
from tools.pipeline_eval.variants.experimental.receiver_benchmark import (
    Factor,
    Receiver,
    read_simulated_prefix,
)
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_build import build, replace

work = Path("/tmp/leo-algo08v2-2x-bench")
assets = Path("/opt/leo-algo08/current/assets")
stock, repair = work / "receiver-stencil.so", work / "receiver-phase-restore-score.so"
original_verify = overlay.verifier_overlay
original_measure = overlay.measurement_overlay


def retain_verifier(source):
    return original_verify(source) + '''
int experimental_reference_score(PortableVerifier *w, unsigned epoch, double hz, double offset,
                                 double *exact, double *control) {
    unsigned flags = 0;
    return glrt(w, epoch, hz, offset, exact, control, NULL, &flags, 0);
}
'''


def retain_measurement(source):
    source = original_measure(source)
    source = replace(source, '    TimingFirst *timing;',
                      '    TimingFirst *timing;\n    unsigned valid_score, approximate_score;\n'
                      '    double score_frequency[2];')
    reset = '\n    r->valid_score = r->approximate_score = 0;'
    source = replace(source, '    if (!r || !out) return -1;',
                      '    if (!r || !out) return -1;' + reset)
    source = replace(source, '    double radius[2] = {0.};',
                      '    double radius[2] = {0.};' + reset)
    source = replace(source, '        radius[count] = portable_verifier_margin_radius(r->verify);',
                     '''        radius[count] = portable_verifier_margin_radius(r->verify);
        r->valid_score |= 1u << i;
        if (radius[count] > 0.) r->approximate_score |= 1u << i;
        r->score_frequency[i] = p[i].hz;''')
    return source + '''
int experimental_reference_score(PortableVerifier *, unsigned, double, double, double *, double *);

int experimental_repair_selected_score(TwoCarrierReceiver *r, ScanFactor *row) {
    if (!r || !row || row->rank < 0 || row->rank > 1 || row->integer < 0 || row->integer >= period)
        return -1;
    unsigned bit = 1u << row->rank;
    if (!(r->valid_score & bit)) return -1;
    if (!(r->approximate_score & bit)) return 0;
    if (experimental_reference_score(r->verify, (unsigned)row->integer,
                                     r->score_frequency[row->rank], row->offset,
                                     &row->exact, &row->control)) return -1;
    return 1;
}
'''


def measured(rows, *, project_only=False):
    with ExitStack() as stack:
        receivers = {}
        for edge in sorted({row["edge"] for row, _ in rows}):
            pilot = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            arms = [Receiver(path, pilot) for path in (stock, repair)]
            for arm in arms:
                stack.callback(arm.close)
            native = arms[1].lib.experimental_repair_selected_score
            native.argtypes = [ct.c_void_p, ct.POINTER(Factor)]
            native.restype = ct.c_int
            receivers[edge] = arms, native
        repeat = []
        for order in range(2):
            cpu, count, costs = [0, 0], Counter(), []
            history = defaultdict(Continuation)
            for index, (row, iq) in enumerate(rows):
                a, target = row["acquisition"], row["target"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - a["actual_if_center_hz"]
                arms, native = receivers[row["edge"]]
                for lane in (0, 1):
                    first = (index + lane + order) % 2
                    factors, selects = [None, None], [None, None]
                    for arm in (first, 1 - first):
                        factors[arm], elapsed, _ = arms[arm].timed(iq, lane, center)
                        cpu[arm] += elapsed
                        probe = dict(receiver_id=lane, channel=target["channel"],
                                     actual_rf_hz=a["actual_if_center_hz"]+target["lnb_lo_hz"],
                                     valid_start_counter=a["sample_start"],
                                     candidates=[arms[arm].criteria(*p) for p in factors[arm]])
                        selects[arm] = history[(arm, row["case"])].select(probe)[1]
                    if selects[0] != selects[1]:
                        raise ValueError("continuation decision changed")
                    checked = range(len(factors[0])) if project_only else (
                        [] if selects[0] is None else [selects[0]])
                    for index_of_factor in checked:
                        count["selected_for_check"] += 1
                        previous, new = [result[index_of_factor] for result in factors]
                        restored = Factor(*new)
                        args = arms[1].ctx, ct.byref(restored)
                        start = process_time_ns()
                        status = native(*args)
                        cost = process_time_ns() - start
                        if status < 0:
                            raise ValueError("cannot recover the stock fractional score")
                        if status:
                            costs.append(cost)
                        if (restored.rank, restored.integer, restored.offset, restored.hz,
                                restored.exact, restored.control) != previous:
                            raise ValueError("exact score reconstruction differs")
            repeat.append(dict(cpu_s=[v / 1e9 for v in cpu],
                               scores_checked=count["selected_for_check"], restored=len(costs),
                               repair_cpu_s=sum(costs)/1e9, repair_ns=costs))
        return repeat


if sys.argv[1] == "build":
    with (
        patch.object(overlay, "verifier_overlay", retain_verifier),
        patch.object(overlay, "measurement_overlay", retain_measurement),
    ):
        build(repair, pack_stencil=True, phase_free=True)
elif sys.argv[1] == "physical":
    binding = Path("/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0016.json")
    rows = list(read_physical(binding, Path("/srv/bulk"), 128))
    print(json.dumps(measured(rows), indent=2))
else:
    public = Path("/tmp/leo-regional-qZJKBw4W/public/panel.json")
    rows = [(row, iq) for row, iq in read_simulated_prefix(public, 40)
            if row["case"] == "6bd1f26bfa0bedfcf3f100f8"]
    print(json.dumps(measured(rows, project_only=True), indent=2))

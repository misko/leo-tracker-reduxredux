"""Matched finer timing precision after the preserved 0.1-second pilot."""

from pathlib import Path
import probe_ds23_phase_measurement_design as engine
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=engine.OUT/'finer_precision'
BULK=Path('/srv/bulk/leo/research/ds23-phase-measurement-precision-20261021')
ORIGINAL_PREPARE=engine.prepare


def prepare():
    protocol=ORIGINAL_PREPARE()
    workflow=dict(hypothesis='Determine whether tighter independent timing can replace measuring every family',
        source_pilot_sha256=sha(ROOT/'reports/2026_10_21_ds23_phase_measurement_design/pilot_evaluation.json'),
        matched_original_simulations_and_independent_timing_standard_normal_draws=True,
        original_pilot_and_coarse_protocol_preserved=True,
        source_tools={Path(__file__).name:sha(Path(__file__))},real_DS23_accuracy_gain=False)
    path=OUT/'workflow_protocol.json'
    if path.exists() and read(path)!=workflow:raise ValueError('finer timing precision protocol changed')
    if not path.exists():write(path,workflow)
    return protocol


def main():
    engine.OUT=OUT;engine.BULK=BULK;engine.prepare=prepare
    engine.VARIANTS={f'information_{k}_sd002':dict(method='information',budget=k,sigma_s=.02) for k in [1,3,6]}
    engine.VARIANTS.update(information_all_sd002=dict(method='information',budget=10000,sigma_s=.02),
        point_count_3_sd002=dict(method='point_count',budget=3,sigma_s=.02),
        random_3_sd002=dict(method='random',budget=3,sigma_s=.02))
    engine.main()


if __name__=='__main__':main()

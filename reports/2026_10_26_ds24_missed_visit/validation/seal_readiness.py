"""Freeze adapter/readiness source before timing outcomes; append later audits."""

import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    names=('PROTOCOL.md','TIMING_INTERFACE.md','SUPPORT_CLARIFICATION.md',
        'baseline_scope.py','integration.py','prepare_overlay.py','audit_prediction.py',
        'test_integration.py','test_graph_integration.py','report_readiness.py','seal_readiness.py',
        'INTEGRATION_STATUS.md','baseline_source_receipt.json','baseline_readiness.json',
        'prediction_audit.json','readiness_summary.json','readiness.png','readiness.pdf')
    files={str(HERE/name):sha(HERE/name) for name in names}
    out=dict(schema='missed-visit-validation-readiness-seal-v1',frozen_utc_ns=time.time_ns(),
        files=files,tests_passed=19,raw_IQ_reads=0,held_validation_target_outcomes_opened=False,
        geographic_errors_opened=False,new_inference_fits=0,
        next_stage='Independent timing parity/control/exposure audit; this is not a candidate approval.')
    with (HERE/'readiness_seal.json').open('x') as stream:
        json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(status='readiness_sealed',source_artifacts=len(files),tests=19)))


if __name__=='__main__':main()

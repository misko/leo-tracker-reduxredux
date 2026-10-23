"""Render the standard DBG01 atlas from independently audited018 evidence."""
from pathlib import Path
import report_ds23_dbg01_iteration_016 as renderer
import probe_ds23_iteration018_recovery as binding


def configure():
    renderer.binding=binding;renderer.runner=binding.runner;renderer.paths=binding.paths.paths
    renderer.RAW=binding.runner.RAW;renderer.OUT=Path(__file__).resolve().parents[2];renderer.ITERATION=18
    renderer.INCLUDE_INDEPENDENT=True
    renderer.METHODS=['Incumbent','Graph recovery','Persistent temporal','Independent predictive','Extra curve']
    renderer.SOURCES=['run_ds23_dbg01_iteration_018.py','probe_ds23_iteration018_recovery.py',
        'audit_ds23_iteration016_recovery.py','audit_ds23_iteration014_recovery.py',
        'report_ds23_dbg01_iteration_016.py','ds23_distributed_polynomial_curvature.py']
    renderer.TESTS=['test_ds23_dbg01_iteration_018.py','test_ds23_iteration018_recovery.py',
        'test_ds23_iteration016_audit.py','test_ds23_distributed_polynomial_curvature.py']


if __name__=='__main__':configure();renderer.main()

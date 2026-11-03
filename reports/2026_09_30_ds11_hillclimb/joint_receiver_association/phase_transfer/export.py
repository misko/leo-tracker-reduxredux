"""Reuse the audited exporter with this independently frozen donor scope."""
import importlib.util
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('phase_transfer_export',HERE.parent/'frame_evolution/export.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.HERE=HERE

if __name__=='__main__':
    index=int(sys.argv[1])
    assert index in (18,20,7,11,4,19,0,10,5,14)
    module.main(index)

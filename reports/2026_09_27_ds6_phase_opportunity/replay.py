"""Use the frozen validated extractor on the new preselected metadata plans."""
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('replay',HERE.parent/'2026_09_27_ds6_phase_expansion/replay.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.HERE=HERE
if __name__=='__main__':module.main()

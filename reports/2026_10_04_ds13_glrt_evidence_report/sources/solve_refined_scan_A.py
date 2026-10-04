"""Regenerate satellite timing pool on refined data with frozen RX calibration."""
import json,argparse
from pathlib import Path
import numpy as np
import absolute_timing_solver as s
from replay import NAMESPACE,digest

SOURCE=NAMESPACE/'full-scan-A-refinement/refined.json'
class RefinedCalibration(s.AbsoluteCalibration):
    def __init__(self):
        super().__init__();receipt=json.loads(SOURCE.read_text())
        for path,h in receipt['sources'].items():assert digest(Path(path))==h
        values={r['row_index']:r['output_hz'] for r in receipt['records']}
        assert set(values)==set(self.d.original_rows)
        self.d.measured=np.array([values[int(i)] for i in self.d.original_rows])
        for d,_ in self.parts:d.measured=np.array([values[int(i)] for i in d.original_rows])
        self.sources[str(SOURCE)]=digest(SOURCE);self.sources[str(Path(__file__))]=digest(Path(__file__))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['discover','solve']);parser.add_argument('--arm',choices=['fitted-c','zero-c']);a=parser.parse_args()
    s.OUT=NAMESPACE/'full-scan-A-refinement/solver';s.AbsoluteCalibration=RefinedCalibration
    if a.stage=='discover':s.discover('A')
    else:s.solve('A',a.arm,3)

if __name__=='__main__':main()

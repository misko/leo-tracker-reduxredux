"""Learn within-track radio covariance from saved GLRT graph curves."""

import argparse
from pathlib import Path
from ds23_radio_correlation import learn
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/"reports/2026_10_19_algo03_radio_correlation"
SOURCE=ROOT/"reports/2026_10_19_algo02_ds23_full"


def run(case):
    OUT.mkdir(exist_ok=True);path=OUT/(case+".json")
    if path.exists():raise FileExistsError("preserve radio qualification")
    tracks=SOURCE/case/"tracks.json";selection=learn(read(tracks))
    write(path,dict(case=case,selection=selection,tracks_sha256=sha(tracks),
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/"tools/ds23_radio_correlation.py")))
    print(case,selection["qualified"],selection["alpha"],selection["tau_s"],selection.get("radio_REML_gain"),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case",required=True)
    run(parser.parse_args().case)

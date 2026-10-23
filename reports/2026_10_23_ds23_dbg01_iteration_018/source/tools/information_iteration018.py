"""Local nuisance-projected information; no new fit or confidence claim."""
from pathlib import Path
import shutil
import review_ds23_worst_outliers as diagnostic
import run_ds23_dbg01_iteration_018 as runner
from run_algo01_ds23_sample import ROOT,read


def main():
    out=ROOT/'reports/2026_10_23_ds23_dbg01_iteration_018'
    runner.configure()
    cases=read(runner.RAW/'protocol.json')['cases']
    for case in cases:
        folder=out/'evidence'/case;folder.mkdir(exist_ok=True)
        shutil.copyfile(runner.RAW/case/'DBG01/audit.json',folder/'DBG01_audit.json')
    diagnostic.OUT=out;diagnostic.SOURCE=out;diagnostic.CASES=cases
    diagnostic.setup=runner.engine.current_setup;diagnostic.build=runner.engine.baseline.build
    diagnostic.main()


if __name__=='__main__':main()

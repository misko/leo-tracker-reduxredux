"""Invoke the unchanged DS27 time-gap adapter for a named DS26 source."""
import json
from pathlib import Path
import sys
sys.path.insert(0,'/srv/bulk/leo/research/ds27-confident-recovery-20261031')
import gap_stage

if __name__=='__main__':
    if sys.argv[1]=='prepare':
        gap_stage.STUDY=Path(sys.argv[2]);target=json.loads(sys.argv[3]);target['case']='.'
        gap_stage.prepare(target)
    else:gap_stage.execute(gap_stage.RELEASE/'tools'/sys.argv[1],sys.argv[2:])

"""Graph component process with current graph code and UID1000 dependencies."""
import argparse
from pathlib import Path
import sys
import application as app

def main(case):
    assert __import__('os').getuid()==1000
    protocol=app.read(app.HERE/'graph_protocol_v2.json')
    for path,h in protocol['files'].items():assert app.sha(path)==h,path
    sys.path.insert(0,str(app.R01/'validation'))
    from prepare_overlay import rebuild_graph
    ledger=app.read(app.HERE/'ledgers'/(case+'_additions.json'))
    config=app.read(Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json'))['config']
    tracks,g=rebuild_graph(ledger['observations'],case,config)
    folder=app.HERE/'graph_work'/case;folder.mkdir(parents=True,exist_ok=False)
    app.write(folder/'tracks.json',tracks);app.write(folder/'graph.json',g)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);main(p.parse_args().case)

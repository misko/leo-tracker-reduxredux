"""Independent native host chain from freshly reprocessed raw-IQ GLRT controls."""
import json
from pathlib import Path
import subprocess
import time

from evaluate_three_recorded_scans import host_projection, load_reference, digest, save


def main():
    root=Path(__file__).resolve().parents[1];report=root/'reports/2026_10_01_arm_three_scan_sequence'
    for index,scan in enumerate(json.loads((report/'selection.json').read_text())['scans']):
        directory=report/scan['session_id'];output=directory/'native-host-pipeline-v2';output.mkdir()
        calls=load_reference(directory/'native-host-glrt')
        if len(calls)!=scan['visits']:raise ValueError('incomplete native detector replay')
        # An explicitly labelled candidate adapter, with no invented hardware timings.
        rows=[{'sequence':i,'candidates':cs} for i,cs in enumerate(calls)]
        rows.append({'kind':'native_host_candidate_adapter_summary','visits':len(calls)})
        (output/'detector.stdout').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        authority=[l.split('\t') for l in (directory/('prepared-reuse' if index==0 else 'prepared')/'authority.tsv').read_text().splitlines()]
        began=time.monotonic();hashes=host_projection(output,scan,authority,output,compare_to_arm=False)
        times={'projection':time.monotonic()-began}
        commands={
            'seeds':[root/'reports/2026_09_30_arm_fast_tracks/grid/grid-trial-v3',output/'observations.tsv',151,8,512,8,4,16],
            'tracks':[root/'reports/2026_09_30_arm_curvature_tracks/hybrid-v1/artifacts/leo-curvature-tracks',output/'observations.tsv','--acceleration',250,'--seeds',output/'seeds.stdout'],
            'search':['/var/tmp/leo-three-position-host',output/'observations.tsv',output/'graph.tsv',output/'tracks.stdout',directory/'native-orbit/selected.tle',-60,10,43,38.5816,-121.4944,250,1,output/'associations.json']}
        for name,command in commands.items():
            began=time.monotonic()
            with (output/(name+'.stdout')).open('x') as out,(output/(name+'.stderr')).open('x') as err:
                subprocess.run(list(map(str,command)),stdout=out,stderr=err,check=True,timeout=180)
            times[name]=time.monotonic()-began
        save(output/'receipt.json',{'status':'complete','session':scan['session_id'],'capture_digest':scan['manifest_sha256'],
            'visits':len(calls),'input_receipt_sha256':digest(directory/'native-host-glrt/receipt.json'),
            'projection_sha256':hashes,'wall_s':times,'commands':{k:list(map(str,v)) for k,v in commands.items()},
            'binary_sha256':{k:digest(v[0]) for k,v in commands.items()},
            'scope':'Fresh host GLRT from original raw IQ feeds all subsequent native modules; independent of ARM outputs'})
        print(scan['session_id']+' complete',flush=True)


if __name__=='__main__':main()

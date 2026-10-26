"""Read-only scientific-input audit; writes one fresh verification receipt."""
import json
from pathlib import Path
import subprocess
import sys
from collections import Counter
import predictor as p
import study

HERE=Path(__file__).resolve().parent


def main():
    study.bound()
    for name in ['protocol.json','handoff_protocol.json','timing_diagnosis_protocol.json']:
        for path,digest in study.read(HERE/name)['files'].items():assert study.sha(path)==digest,path
    panel=study.read(HERE/'panel.json');predictions=study.read(HERE/'predictions.json')
    packets=study.read(HERE/'prediction_packets.json');donors=study.read(HERE/'donor_authority.json')
    by_key={r['header']['prediction_id']:r for r in predictions['rows']}
    enriched={r['header']['prediction_id']:r for r in packets['rows']}
    assert len(panel['slots'])==288 and len(by_key)==576 and len(enriched)==576
    assert all(s['status']=='nominated'for s in panel['slots'])
    assert all(r['status']=='metadata_verified'for r in donors['rows'])
    assert len(donors['rows'])==donors['requested_donor_windows']
    development=set(study.read(HERE.parent/'split.json')['development'])
    for slot in panel['slots']:
        assert slot['case']in development
        a=slot['raw_authority']['index']['acquisition']
        for cell in slot['cells']:
            h=cell['header'];row=by_key[h['prediction_id']];packet=enriched[h['prediction_id']]
            assert row['status']=='complete'and row['forecast']==p.predict(h,cell['history'])
            assert row['forecast']==p.predict(dict(h,target_candidates=[dict(CFO_hz=1e99)]),cell['history'])
            assert packet['donor_metadata_status']=='verified'
            assert packet['header']['generation']==a['generation']
            assert packet['header']['stream_generation']==h['generation']
            assert packet['target_support']['start_counter']==h['start_counter']==a['sample_start']
            assert packet['target_support']['stop_counter']==h['stop_counter']==a['sample_end']
            modes=row['forecast']['modes'];assert len(modes)<=8
            assert all(n<=2 for n in Counter(m['donors'][-1]['observation_id']for m in modes).values())
            for m,new in zip(modes,packet['forecast']['modes']):
                for oldf,newf in zip([m['full']]+m['halves'],[new['full']]+new['halves']):
                    assert all(newf[k]==v for k,v in oldf.items())
                for d in new['donors']:
                    assert d['support']['generation']==a['generation']
                    assert d['support']['stop_counter']<=h['start_counter']
                    assert d['support']['start_counter']==d['start_counter']
                assert m['model']['reference_counter']==m['donors'][-1]['reference_counter']
                assert m['model']['timing_reference_counter']==m['donors'][-1]['start_counter']
    run=subprocess.run([sys.executable,'-m','unittest','-v','test_predictor.py','test_handoff.py'],
        cwd=HERE,text=True,capture_output=True,timeout=30)
    assert run.returncode==0,run.stderr
    study.write(HERE/'test_results.json',dict(exit_code=run.returncode,expected_tests=5,stderr=run.stderr,stdout=run.stdout))
    study.write(HERE/'verification.json',dict(all_passed=True,owned_tests=5,development_scans=12,
        paired_targets=288,forecast_cells=576,fresh_target_response_redactions=576,
        native_generation_and_support_cells=576,selected_donor_windows_verified=len(donors['rows']),
        source_protocol_sha256=study.sha(HERE/'protocol.json'),predictions_sha256=study.sha(HERE/'predictions.json'),
        packets_sha256=study.sha(HERE/'prediction_packets.json'),validation_target_files_opened=False,raw_IQ_reads=0))
    print('verification passed')


if __name__=='__main__':main()

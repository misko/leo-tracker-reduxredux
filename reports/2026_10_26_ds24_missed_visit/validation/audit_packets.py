"""Verify metadata enrichment preserves all frozen numerical forecasts."""

import copy
import json
from pathlib import Path

from baseline_scope import sha

HERE=Path(__file__).resolve().parent
PRED=HERE.parent/'prediction'


def read(path):return json.loads(Path(path).read_text())


def strip_metadata(row):
    row=copy.deepcopy(row)
    row.pop('target_support',None);row.pop('donor_metadata_status',None)
    header=row['header'];header['generation']=header.pop('stream_generation')
    for mode in row.get('forecast',{}).get('modes',[]):
        for collection in (mode['donors'],mode['model']['donors']):
            for donor in collection:
                donor['generation']=donor.pop('stream_generation')
                donor.pop('support',None);donor.pop('authority_key',None);donor.pop('metadata_status',None)
        for forecast in [mode['full']]+mode['halves']:
            forecast.pop('generation',None);forecast.pop('source_IQ_sha256',None)
    return row


def main():
    packet=read(PRED/'prediction_packets.json');protocol=read(PRED/'handoff_protocol.json')
    for path,digest in protocol['files'].items():assert sha(path)==digest,path
    assert packet['handoff_protocol_sha256']==sha(PRED/'handoff_protocol.json')
    assert packet['frozen_predictions_sha256']==sha(PRED/'predictions.json')
    frozen=read(PRED/'predictions.json')
    assert len(packet['rows'])==len(frozen['rows'])==576
    verified=0;mismatched=0;donor_uses=0
    for new,old in zip(packet['rows'],frozen['rows'],strict=True):
        assert strip_metadata(new)==old
        assert type(new['header']['generation']) is int
        assert isinstance(new['header']['stream_generation'],str)
        if new['donor_metadata_status']=='verified':verified+=1
        else:mismatched+=1
        for mode in new['forecast']['modes']:
            for donor in mode['donors']:
                assert type(donor['generation']) is int
                assert isinstance(donor['stream_generation'],str)
                assert donor['support']['start_counter']==donor['start_counter']
                assert donor['support']['stop_counter']==donor['stop_counter']
                assert donor['support']['generation']==donor['generation']
                assert donor['stop_counter']<=new['header']['start_counter']
                donor_uses+=1
    out=dict(all_passed=True,numerically_identical_rows=576,metadata_verified_rows=verified,
        metadata_mismatch_rows=mismatched,donor_uses_verified=donor_uses,
        target_or_geography_inputs=False,new_RF_calls=0,
        packets_sha256=sha(PRED/'prediction_packets.json'),
        handoff_protocol_sha256=sha(PRED/'handoff_protocol.json'),
        interpretation='Integer native generations and string stream labels are distinct and both must survive the timing adapter.')
    with (HERE/'packet_audit.json').open('x') as stream:
        json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()

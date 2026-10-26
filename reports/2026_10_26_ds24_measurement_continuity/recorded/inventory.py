"""Read-only inventory of original winning GLRT and nearby exported proposals."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from ds23_frame_registration import unique_peaks

HERE=Path(__file__).resolve().parent
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024/DS24-0011')
PERIOD=1/4.4e-6


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wrap(x, period):
    return (x+period/2)%period-period/2


def csv_write(name,rows):
    with (HERE/name).open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def main():
    assert not (HERE/'summary.json').exists(), 'preserve original inventory'
    assert sha(SOURCE/'tracking.json')=='a0b25c6abea7979f935ce2eaf8b289eb1831b206a6deca65854817e91c8a85f5'
    bound=[SOURCE/name for name in ('tracking.json','observations.json','tracks.json')]
    bound += [HERE/'INVENTORY.md',HERE/'inventory.py',
        Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/ds23_frame_registration.py')]
    protocol=dict(files={str(p):sha(p) for p in bound},maximum_epoch_distance_samples=3,
        minimum_CFO_distance_exclusive_hz=250,maximum_CFO_distance_hz=5000,
        margin_ratio_gate=None,identity_inference=False,position_evaluation=False)
    (HERE/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    document=json.loads((SOURCE/'tracking.json').read_text())
    observations=json.loads((SOURCE/'observations.json').read_text())
    tracks=json.loads((SOURCE/'tracks.json').read_text())
    source=document['source'];fs=source['sample_rate_hz']
    origin=document['clock_anchor']['sample_counter']
    index={(r['native_receiver_id'],r['channel'],round(r['time_s'],9)):r for r in observations}
    assert len(index)==len(observations)==3754
    memberships={}
    for track in tracks:
        for oid in track['observation_ids']:
            assert oid not in memberships
            memberships[oid]=track['key']
    winners,alternatives=[],[]
    for probe in source['probes']:
        eligible=[c for c in probe['candidates'] if c['passed_fractional_margin_gate'] is True]
        if not eligible:continue
        best=max(eligible,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
        time_s=(probe['valid_start_counter']-origin)/fs+probe['probe_start_ms']/1000+source['probe_ms']/2000
        row=index[probe['receiver_id'],probe['channel'],round(time_s,9)]
        assert row['measured_cfo_hz']==best['fractional_tracking_cfo_hz']
        assert row['fractional_margin']==best['fractional_margin']
        epoch=best['integer_epoch_sample']+best['fractional_epoch_offset_samples']
        nearby=[]
        for candidate in unique_peaks(probe['candidates'],fs):
            delta_epoch=wrap(candidate['epoch']-epoch,fs/750)
            raw_delta=candidate['cfo']-best['fractional_tracking_cfo_hz']
            delta=wrap(raw_delta,PERIOD)
            if abs(delta_epoch)<=3 and 250<abs(delta)<=5000:
                detail=dict(observation_id=row['observation_id'],owner=memberships.get(row['observation_id'],''),
                    receiver=row['receiver'],channel=row['channel'],time_s=time_s,
                    winning_candidate_rank=best['candidate_rank'],alternative_rank=candidate['rank'],
                    winner_CFO_hz=best['fractional_tracking_cfo_hz'],alternative_CFO_hz=candidate['cfo'],
                    raw_CFO_delta_hz=raw_delta,circular_CFO_delta_hz=delta,
                    circular_epoch_delta_samples=delta_epoch,
                    winner_margin=best['fractional_margin'],alternative_margin=candidate['margin'],
                    margin_ratio=candidate['margin']/best['fractional_margin'])
                nearby.append(detail);alternatives.append(detail)
        winners.append(dict(observation_id=row['observation_id'],owner=memberships.get(row['observation_id'],''),
            receiver=row['receiver'],channel=row['channel'],time_s=time_s,
            winner_CFO_hz=best['fractional_tracking_cfo_hz'],winner_margin=best['fractional_margin'],
            winner_rank=best['candidate_rank'],exported_candidate_count=len(probe['candidates']),
            deduplicated_count=len(unique_peaks(probe['candidates'],fs)),proximity_flag=bool(nearby),
            nearby_alternative_count=len(nearby)))
    assert len(winners)==len(observations)
    assert {r['observation_id'] for r in winners}=={r['observation_id'] for r in observations}
    by_id={r['observation_id']:r for r in winners}
    owners=[]
    for track in tracks:
        rows=[by_id[oid] for oid in track['observation_ids']]
        count=sum(r['proximity_flag'] for r in rows)
        owners.append(dict(owner=track['key'],receiver=track['receiver'],channel=track['channel'],
            original_points=len(rows),flagged_points=count,flagged_fraction=count/len(rows),
            start_s=track['start_s'],end_s=track['end_s'],original_quality_status=track['quality_status']))
    target=next(r for r in owners if '-RX1-CH1-T006-' in r['owner'])
    channels=[]
    counts=np.zeros((2,8));totals=np.zeros((2,8))
    for r in winners:
        totals[r['receiver']-1,r['channel']-1]+=1
        counts[r['receiver']-1,r['channel']-1]+=r['proximity_flag']
    for rx in range(2):
        for ch in range(8):
            channels.append(dict(receiver=rx+1,channel=ch+1,winning_points=int(totals[rx,ch]),
                flagged_points=int(counts[rx,ch]),flagged_fraction=float(counts[rx,ch]/totals[rx,ch]) if totals[rx,ch] else None))
    csv_write('winners.csv',winners);csv_write('owners.csv',owners);csv_write('channels.csv',channels)
    if alternatives:csv_write('alternatives.csv',alternatives)
    fig,axes=plt.subplots(2,1,figsize=(11.8,7.2),gridspec_kw={'height_ratios':[1,1.6]})
    image=axes[0].imshow(100*np.divide(counts,totals,out=np.zeros_like(counts),where=totals>0),
        aspect='auto',cmap='Blues',vmin=0,vmax=100)
    for rx in range(2):
        for ch in range(8):
            axes[0].text(ch,rx,f'{int(counts[rx,ch])}/{int(totals[rx,ch])}',ha='center',va='center',fontsize=9)
    axes[0].set_yticks([0,1],['RX1','RX2']);axes[0].set_xticks(range(8),[f'CH{i}' for i in range(1,9)])
    axes[0].set_title('Winners with at least one nearby exported proposal / all original winners')
    fig.colorbar(image,ax=axes[0],label='Proximity-flagged winners (%)',pad=.02)
    own=[r for r in winners if r['owner']==target['owner']]
    axes[1].scatter([r['time_s'] for r in own],np.zeros(len(own)),color='black',s=25,label='Original selected T006 points')
    alt=[r for r in alternatives if r['owner']==target['owner']]
    for r in alt:
        axes[1].plot([r['time_s']]*2,[0,r['circular_CFO_delta_hz']],color='#d47a3a',alpha=.5,lw=1)
    if alt:
        axes[1].scatter([r['time_s'] for r in alt],[r['circular_CFO_delta_hz'] for r in alt],
            color='#d47a3a',s=25,label='Nearby alternative minus winner (circular CFO)')
    axes[1].set_ylim(-5500,5500);axes[1].axhline(0,color='black',lw=.6)
    axes[1].set_title(f"DS24-0011 RX1 CH1 T006: {target['flagged_points']}/{target['original_points']} points flagged")
    axes[1].set_xlabel('Original scan time (s)');axes[1].set_ylabel('Alternative − winner (Hz)')
    axes[1].grid(alpha=.2);axes[1].legend(fontsize=9)
    fig.suptitle('Recorded-export inspection proposals; not confirmed multiple sources',fontsize=14)
    fig.text(.5,.012,'Existing candidates only. ≤3 frame samples and (250, 5,000] Hz circular separation. No satellite, IQ or position inference.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.95))
    fig.savefig(HERE/'proximity_inventory.png',dpi=180);fig.savefig(HERE/'proximity_inventory.pdf');plt.close(fig)
    result=dict(original_probes=len(source['probes']),winning_points=len(winners),original_owners=len(owners),
        flagged_winners=sum(r['proximity_flag'] for r in winners),flagged_owner_count=sum(r['flagged_points']>0 for r in owners),
        nearby_alternative_records=len(alternatives),target=target,channels=channels,
        no_new_detector_calls=True,no_new_IQ_read=True,no_position_or_identity_inference=True,
        inputs_sha256=protocol['files'])
    (HERE/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    files=[p for p in HERE.iterdir() if p.is_file() and p.name!='seal.json']
    (HERE/'seal.json').write_text(json.dumps({p.name:sha(p) for p in sorted(files)},indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'channels','inputs_sha256'}}))


if __name__=='__main__':main()

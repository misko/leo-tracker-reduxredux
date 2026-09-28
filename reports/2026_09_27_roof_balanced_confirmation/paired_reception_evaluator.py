"""Fixed-frequency paired reception-calibration replay, research only."""
from collections import defaultdict
import numpy as np
import run_balanced_confirmation as runner
from robust_core import train_shortlist, joint_heldout_score


def score_variants(predictions, east, measured, training, shortlist, variants):
    scores={name:joint_heldout_score(predictions,east,measured,training,shortlist,rows,
        ratio_variance=variance) for name,(rows,variance) in variants.items()}
    d=[s['scores']['D'] for s in scores.values()]
    if not d or not np.allclose(d,d[0],rtol=0,atol=1e-12):
        raise ValueError('reception variants changed frequency score')
    return scores


class PairedEvaluator(runner.frozen.original.RobustBranchEvaluator):
    def __init__(self,banks,origin,variants,parameters):
        first=next(iter(variants.values()))
        super().__init__(banks,origin,first[0],first[1],parameters)
        self.variants=variants

    def evaluate(self,east,north):
        key=(float(east),float(north))
        if key in self.cache:return self.cache[key]
        lat,lon=runner.base.coordinates(*self.origin,*key)
        receiver=runner.base.point(lat,lon).ecef_km
        east_axis=np.array([-np.sin(np.deg2rad(lon)),np.cos(np.deg2rad(lon)),0.])
        blocks=defaultdict(list)
        for block in self.predictions(*key):blocks[block.track_id].append(block)
        totals={name:defaultdict(float) for name in self.variants};weight_sum=0
        for tid,bank in self.banks.items():
            track=bank.source;chunks=blocks[tid]
            predictions=np.concatenate([b.predictions_hz[:,0,:] for b in chunks])
            ids=np.concatenate([b.candidate_ids for b in chunks])
            visible=np.concatenate([b.visible for b in chunks])
            shortlist=train_shortlist(predictions,track.measured_hz,track.training_mask,visible,
                scale_hz=self.parameters['scale_hz'],df=self.parameters['degrees_of_freedom'])
            indices=np.asarray(shortlist['candidate_indices']);chosen_ids=ids[indices]
            short=dict(shortlist,candidate_indices=list(range(len(indices))))
            positions=bank.position_km[[self.index[tid][int(cid)] for cid in chosen_ids],0,:,:]
            delta=positions-receiver;direction=delta/np.linalg.norm(delta,axis=-1,keepdims=True)
            variants={name:(rows[tid],variance) for name,(rows,variance) in self.variants.items()}
            values=score_variants(predictions[indices],np.sum(direction*east_axis,axis=-1),
                track.measured_hz,track.training_mask,short,variants)
            weight=len(np.unique(np.floor(track.times_s)));weight_sum+=weight
            for name,result in values.items():
                for arm,value in result['scores'].items():totals[name][arm]+=weight*value
        row=dict(east_km=key[0],north_km=key[1],latitude_deg=lat,longitude_deg=lon,
            weight_seconds=weight_sum,variant_scores={name:{arm:total/weight_sum for arm,total in arms.items()}
                for name,arms in totals.items()})
        self.cache[key]=row
        return row

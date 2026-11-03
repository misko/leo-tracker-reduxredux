"""Normalized track-scale transformation of the unchanged q020 likelihood."""
import importlib.util
import math
from pathlib import Path
import numpy as np

REPORTS=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('scale_budget',REPORTS/'2026_09_29_scan_budget/run.py')
budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget)
helper=budget.helper
trend_module=__import__('trend_mixture')


class Scaled:
    def __init__(self,documents,config,ratios,factory=None):
        factory=factory or helper.baseline.Stationary
        transformed=[];self.corrections={};self.total=0.
        for doc in documents:
            tracks=[]
            for track in doc['tracks']:
                key=(doc['session_id'],track['track_id'])
                ratio=float(ratios.get(key,1.))
                if not np.isfinite(ratio) or ratio<=0:
                    raise ValueError('Scale ratios must be positive and finite')
                tracks.append(dict(track,y=track['y']/ratio,scale_ratio=ratio))
                training=(int(track['mask'].sum())-1)*math.log(ratio)
                held=int((~track['mask']).sum())*math.log(ratio)
                self.corrections[key]=(training,held)
                self.total+=training
            transformed.append(dict(doc,tracks=tracks))
        class Engine:
            def __init__(self,doc,config):
                self.engine=factory(doc,config)
            def coordinates(self,x):
                return self.engine.coordinates(x)
            def prediction(self,track,x):
                values,visible=self.engine.prediction(track,x)
                return values/track['scale_ratio'],visible
        self.inner=helper.TrendMixturePosition(transformed,config,Engine,.2)
        self.models=self.inner.models
        for di,doc in enumerate(transformed):
            for ti,track in enumerate(doc['tracks']):
                mask=track['mask'];times=np.asarray(track['times_s'])
                slope=2000./track['scale_ratio']
                self.inner.background[di,ti]=(trend_module.trend_density(track['y'][mask],times[mask],100.,slope),
                                               trend_module.trend_density(track['y'],times,100.,slope))

    def evaluate(self,x,**kwargs):
        out=self.inner.evaluate(x,**kwargs)
        out['score']-=self.total
        for row in out['rows']:
            train,held=self.corrections[row['session_id'],row['track_id']]
            row['training_log_score']-=train
            row['held_log_score']-=held
            row['signal_training_log_density']-=train
            row['background_training_log_density']-=train
        return out

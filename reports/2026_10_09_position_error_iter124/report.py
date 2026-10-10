import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def main():
    data=json.loads((HERE/'evaluation.json').read_text())
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for axis,field,title in zip(axes,['mean_vector_km','coordinate_median_vector_km'],['Mean residual vector (outlier sensitive)','Coordinate median residual vector'],strict=True):
        for group,values in data['summaries'].items():
            for arm,marker in [('fitted-c','o'),('zero-c','x')]:
                east,north=values['arms'][arm][field]
                axis.scatter(east,north,marker=marker,label=f'{group}: {arm}')
        axis.axhline(0,color='gray',lw=.7);axis.axvline(0,color='gray',lw=.7)
        axis.set(title=title,xlabel='East error km',ylabel='North error km',aspect='equal')
    axes[1].legend(fontsize=7,loc='upper left',bbox_to_anchor=(1,1))
    fig.savefig(HERE/'directional-bias.png',dpi=140);plt.close(fig)
    text=['# Shared southward component remains in both c arms','',
          'All 193 consumed development endpoints are included. The fixed chart originates at the first ordinary fitted-c selected endpoint, never at truth. These are descriptive evaluation vectors, not corrections or causal identification.','',
          '![Dataset residual directions](directional-bias.png)','',
          '|Dataset|Arm|Count|Mean east/north km|Median east/north km|RMS norm km|',
          '|---|---|---:|---|---|---:|']
    for group,values in data['summaries'].items():
        for arm,s in values['arms'].items():
            text.append(f"|{group}|{arm}|{s['count']}|{s['mean_vector_km'][0]:.4f}, {s['mean_vector_km'][1]:.4f}|{s['coordinate_median_vector_km'][0]:.4f}, {s['coordinate_median_vector_km'][1]:.4f}|{s['rms_vector_km']:.4f}|")
    text += ['',
        'The full fitted median residual vector is (+0.291 east, -0.377 north) km; c=0 is (+0.382, -0.370) km. Every dataset has a southward median component in both arms. Turning c off does not remove that shared component, which argues against attributing the displacement solely to fitted c. It does not distinguish timing/orbit geometry, hardware bias, selection or other common model errors.',
        '',
        'Full paired fitted-minus-zero mean displacement is (-0.157, -0.040) km. The full mean residual vectors are strongly affected by the retained DS18 failure; all members remain included. Coordinate median and mean describe different estimators, and vector RMS is not an uncertainty estimate.',
        '',
        '**Algebraic coupling:** displacement d = e_fitted - e_zero exactly. Residual/displacement cosine computed from these same endpoints is mechanically coupled, not independent causal evidence. Its alignment cannot establish c-caused bias or identify a physical correction.',
        '',
        'No clock features, weak-direction alignment or baseline-to-candidate displacement were evaluated: gauges and coordinate transport were not admitted. No frequency fit, model call, optimizer, new correction, reserve inspection or standalone accuracy improvement occurred. Full signed vectors and paired quantities: [evaluation.json](evaluation.json).']
    (HERE/'RESULTS.md').write_text('\n'.join(text)+'\n')


if __name__=='__main__':main()

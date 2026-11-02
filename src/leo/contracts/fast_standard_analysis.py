"""Independent presentation publication; scientific ALGO contracts stay immutable."""
import math
import re

MODEL = 'algo07-causal-guarded-reassociation-v1'
PLOTS = ('ch1-4-all', 'ch5-8-all', 'ch1-4-unassociated', 'ch5-8-unassociated',
         'ch1-4-residuals', 'ch5-8-residuals', 'track-rms', 'position')


def validate(document):
    if (document.get('schema_version') != 1 or document.get('model_version') != MODEL
            or document.get('state') != 'complete' or document.get('reference_usage') != 'evaluation_only'):
        raise ValueError('Invalid standard ALGO07 publication')
    for arm in ('c0', 'fitted_c'):
        row = document['arms'][arm]
        if not 0 <= row['associated_points'] <= document['glrt_points']:
            raise ValueError('Invalid native point accounting')
        if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in row['endpoint_latlon']):
            raise ValueError('Invalid standard position')
    if [a['name'] for a in document['artifacts']] != list(PLOTS):
        raise ValueError('Incomplete standard figure inventory')
    for artifact in document['artifacts']:
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',artifact['sha256']) or artifact['byte_count']<=0:
            raise ValueError('Invalid figure digest or size')
    return document

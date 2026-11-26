"""Independent presentation publication; scientific ALGO contracts stay immutable."""
import math
import re
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.algo08v3 import VERSION as ALGO08V3_LABEL, validate_release

MODEL = 'algo07-causal-guarded-reassociation-v1'
ALGO08 = 'algo08-two-scan-compact-v5-v1'
ALGO08V2 = 'algo08-two-scan-compact-v5-v2'
ALGO08V3 = 'algo08-two-scan-compact-v5-v3'
COMPACT_MODELS = (ALGO08, ALGO08V2, ALGO08V3)
REGIONAL_MODELS = (ALGO08V2, ALGO08V3)


def standard_model(run_id):
    if run_id.startswith('algo08-v3-'):
        return ALGO08V3
    if run_id.startswith('algo08-v2-'):
        return ALGO08V2
    return ALGO08 if run_id.startswith('algo08-') else MODEL


def standard_label(model):
    return {ALGO08: 'ALGO08', ALGO08V2: 'ALGO08v2', ALGO08V3: ALGO08V3_LABEL}.get(model, 'ALGO07')


PLOTS = ('ch1-4-all', 'ch5-8-all', 'ch1-4-unassociated', 'ch5-8-unassociated',
         'ch1-4-residuals', 'ch5-8-residuals', 'track-rms', 'position')


def validate(document, *, model=MODEL):
    versions = {MODEL: (1,), ALGO08: (2, 3), ALGO08V2: (3,), ALGO08V3: (3,)}[model]
    if (document.get('schema_version') not in versions or document.get('model_version') != model
            or document.get('state') != 'complete' or document.get('reference_usage') != 'evaluation_only'):
        raise ValueError('Invalid standard analysis publication')
    if document['schema_version'] == 3:
        Algo08Region.parse(document.get('region'))
    if model == ALGO08V3:
        validate_release(document.get('execution_release'))
        if any(document.get(key) != model for key in ('selected_model', 'figures_model')):
            raise ValueError('ALGO08v3 selection and figures must belong to ALGO08v3')
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

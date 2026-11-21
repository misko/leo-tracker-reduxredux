"""Content-addressed standard figures, independent of historical result namespaces."""
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

from leo.contracts.fast_standard_analysis import validate, PLOTS, MODEL, ALGO08
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.position_grid import binding as grid_binding, validate as validate_grid
from leo.contracts.position_path import validate as validate_path
from leo.storage.fast_scan import immutable_json, safe_id
from leo.storage.uri import confined_path

RENDER_REVISION = 'final-error-v7'
PREVIOUS_RENDER_REVISIONS = ('optimizer-path-v6','conditional-grid-v5','diagnostic-position-v4','orbit-layout-v3')

def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


class FastStandardAnalysisStore:
    def model(self, run_id):
        return ALGO08 if run_id.startswith('algo08-') else MODEL

    def __init__(self, root, *, revision=RENDER_REVISION):
        self.root = Path(root).resolve()
        if self.root == Path('/mnt/qnap01') or Path('/mnt/qnap01') in self.root.parents:
            raise ValueError('Standard publication must be local')
        if revision not in (RENDER_REVISION,*PREVIOUS_RENDER_REVISIONS):
            raise ValueError('Unknown standard presentation revision')
        self.revision=revision

    def base_folder(self, run_id):
        namespace = 'fast-scan-standard-v2' if self.model(run_id) == ALGO08 else 'fast-scan-standard-v1'
        return confined_path(self.root, self.root/namespace/safe_id(run_id), must_exist=False)

    def folder(self, run_id):
        return confined_path(self.root, self.base_folder(run_id)/self.revision, must_exist=False)

    def publication_folders(self, run_id):
        base=self.base_folder(run_id)
        if self.model(run_id) == ALGO08:
            return (self.folder(run_id),)
        revisions=(RENDER_REVISION,*PREVIOUS_RENDER_REVISIONS)
        return (*(confined_path(self.root,base/revision,must_exist=False)
            for revision in revisions[revisions.index(self.revision):]),base)

    def detail(self, run_id):
        model = self.model(run_id)
        path=next((folder/'manifest.json' for folder in self.publication_folders(run_id)
                   if (folder/'manifest.json').exists()),None)
        if path is None:
            withheld = self.folder(run_id)/'withheld.json'
            if model == ALGO08 and withheld.is_file():
                return json.loads(withheld.read_bytes())
            return dict(schema_version=2 if model == ALGO08 else 1, run_id=run_id, model_version=model,
                        state='pending', artifacts=[])
        result=validate(json.loads(path.read_text()), model=model)
        ref_path=self.base_folder(run_id)/'evaluation-reference.json'
        result['evaluation_reference']=json.loads(ref_path.read_text()) if ref_path.exists() else None
        for row in result['arms'].values():
            row['evaluation_error_m']=None
            if result['evaluation_reference']:
                ref=result['evaluation_reference'];lat,lon=map(math.radians,row['endpoint_latlon'])
                a,b=map(math.radians,(ref['latitude_deg'],ref['longitude_deg']))
                h=math.sin((lat-a)/2)**2+math.cos(a)*math.cos(lat)*math.sin((lon-b)/2)**2
                row['evaluation_error_m']=6371008.8*2*math.asin(math.sqrt(min(1,max(0,h))))
        return result

    def set_evaluation_reference(self, run_id, latitude_deg, longitude_deg):
        if not (math.isfinite(latitude_deg) and -90<=latitude_deg<=90
                and math.isfinite(longitude_deg) and -180<=longitude_deg<=180):
            raise ValueError('Valid evaluation coordinates required')
        if self.detail(run_id)['state']!='complete':
            raise ValueError('Attach evaluation only after standard inference is complete')
        immutable_json(self.base_folder(run_id)/'evaluation-reference.json',dict(
            source='user-confirmed-evaluation-only',run_id=run_id,latitude_deg=latitude_deg,longitude_deg=longitude_deg))

    def artifact(self, run_id, name, expected=None):
        entry=None
        # Read the latest available layout, or the exact prior digest requested.
        for folder in self.publication_folders(run_id):
            path=folder/'manifest.json'
            if not path.exists():continue
            manifest=validate(json.loads(path.read_text()), model=self.model(run_id))
            entry=next((a for a in manifest['artifacts'] if a['name']==name
                        and (expected is None or a['sha256']==expected)),None)
            if entry is not None:break
            if expected is None:break
        if entry is None:
            raise FileNotFoundError('Standard figure revision unavailable')
        data = (folder/(entry['sha256'].split(':')[1]+'.png')).read_bytes()
        if digest(data) != entry['sha256'] or len(data) != entry['byte_count']:
            raise ValueError('Standard figure integrity failure')
        return data

    def position_grid(self, run_id):
        return self._presentation_evidence(run_id,'position-grid.json',validate_grid)

    def position_path(self, run_id):
        return self._presentation_evidence(run_id,'position-path.json',validate_path)

    def _presentation_evidence(self, run_id, name, validator):
        for folder in self.publication_folders(run_id):
            manifest=folder/'manifest.json'
            if not manifest.exists():continue
            publication=validate(json.loads(manifest.read_text()), model=self.model(run_id))
            path=folder/name
            if not path.exists():return None
            envelope=json.loads(path.read_text())
            if not isinstance(envelope,dict) or 'document' not in envelope or 'sha256' not in envelope:
                raise ValueError('Malformed position grid envelope')
            value=envelope['document']
            raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            if digest(raw)!=envelope['sha256']:raise ValueError('Position grid integrity failure')
            return validator(value,publication)
        return None

    def publish(self, run_id, document, pngs, *, position_grid=None, position_path=None):
        if document.get('run_id')!=run_id:
            raise ValueError('Standard publication belongs to another scan')
        if set(pngs) != set(PLOTS):
            raise ValueError('All standard figures required atomically')
        folder = self.folder(run_id)
        if self.model(run_id) == ALGO08:
            folder.parent.mkdir(parents=True, exist_ok=True)
            if folder.exists():
                old = self.detail(run_id)
                if old.get('terminal_sha256') != document.get('terminal_sha256') or old['state'] != 'complete':
                    raise ValueError('ALGO08 decision already published')
                return old
            with tempfile.TemporaryDirectory(dir=folder.parent) as scratch:
                stage = Path(scratch)/'publication'
                result = self._write_publication(stage, run_id, document, pngs, position_grid, position_path)
                stage.rename(folder)
                return result
        return self._write_publication(folder, run_id, document, pngs, position_grid, position_path)

    def _write_publication(self, folder, run_id, document, pngs, position_grid, position_path):
        if document.get('schema_version') == 3 and (position_grid is None or position_path is None):
            raise ValueError('Regional publication requires its objective grid and recorded path')
        folder.mkdir(parents=True, exist_ok=True)
        entries=[]
        for name in PLOTS:
            data=pngs[name]
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('PNG required')
            sha=digest(data); path=folder/(sha.split(':')[1]+'.png')
            if not path.exists():
                with path.open('xb') as f:
                    f.write(data)
                    f.flush();os.fsync(f.fileno())
            elif path.read_bytes() != data:
                raise ValueError('Figure digest collision')
            entries.append(dict(name=name,sha256=sha,byte_count=len(data)))
        value=validate(dict(document,artifacts=entries), model=self.model(run_id))
        sidecars=[]
        for name,evidence,validator in (('position-grid.json',position_grid,validate_grid),
                                         ('position-path.json',position_path,validate_path)):
            if evidence is not None:
                checked=validator(dict(evidence,binding=grid_binding(value)),value)
                raw=json.dumps(checked,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
                sidecars.append((name,dict(document=checked,sha256=digest(raw))))
        for name,evidence in sidecars:immutable_json(folder/name,evidence)
        immutable_json(folder/'manifest.json',value)
        return value

    def withhold(self, run_id, reason, **provenance):
        if self.model(run_id) != ALGO08 or not reason:
            raise ValueError("Expected a withheld ALGO08 decision and reason")
        if self.detail(run_id)['state'] == 'complete':
            raise ValueError("ALGO08 position already published")
        if 'region' in provenance:
            provenance['region'] = Algo08Region.parse(provenance['region']).document()
        value = dict(**provenance, schema_version=3 if 'region' in provenance else 2, model_version=ALGO08, run_id=run_id,
                     state='withheld', reason=reason, arms={}, artifacts=[])
        immutable_json(self.folder(run_id)/'withheld.json', value)
        return value

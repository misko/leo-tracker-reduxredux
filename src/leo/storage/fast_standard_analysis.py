"""Content-addressed standard figures, independent of historical result namespaces."""
import hashlib
import json
import math
import os
from pathlib import Path

from leo.contracts.fast_standard_analysis import validate, PLOTS
from leo.storage.fast_scan import immutable_json, safe_id
from leo.storage.uri import confined_path

RENDER_REVISION = 'orbit-layout-v3'

def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


class FastStandardAnalysisStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if self.root == Path('/mnt/qnap01') or Path('/mnt/qnap01') in self.root.parents:
            raise ValueError('Standard publication must be local')

    def base_folder(self, run_id):
        return confined_path(self.root, self.root/'fast-scan-standard-v1'/safe_id(run_id), must_exist=False)

    def folder(self, run_id):
        return confined_path(self.root, self.base_folder(run_id)/RENDER_REVISION, must_exist=False)

    def detail(self, run_id):
        path = self.folder(run_id)/'manifest.json'
        if not path.exists():
            return dict(schema_version=1, run_id=run_id, model_version='algo07-causal-guarded-reassociation-v1',
                        state='pending', artifacts=[])
        result=validate(json.loads(path.read_text()))
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
        manifest = self.detail(run_id)
        entry = next((a for a in manifest['artifacts'] if a['name'] == name), None)
        folder = self.folder(run_id)
        # Previously issued digest-qualified URLs retain their immutable bytes.
        if expected is not None and (not entry or expected != entry['sha256']):
            legacy = self.base_folder(run_id)/'manifest.json'
            if legacy.exists():
                old = validate(json.loads(legacy.read_text()))
                entry = next((a for a in old['artifacts'] if a['name']==name and a['sha256']==expected), None)
                folder = self.base_folder(run_id)
        if not entry or (expected is not None and expected != entry['sha256']):
            raise FileNotFoundError('Standard figure revision unavailable')
        data = (folder/(entry['sha256'].split(':')[1]+'.png')).read_bytes()
        if digest(data) != entry['sha256'] or len(data) != entry['byte_count']:
            raise ValueError('Standard figure integrity failure')
        return data

    def publish(self, run_id, document, pngs):
        if document.get('run_id')!=run_id:
            raise ValueError('Standard publication belongs to another scan')
        if set(pngs) != set(PLOTS):
            raise ValueError('All standard figures required atomically')
        folder = self.folder(run_id)
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
        value=validate(dict(document,artifacts=entries))
        immutable_json(folder/'manifest.json',value)
        return value

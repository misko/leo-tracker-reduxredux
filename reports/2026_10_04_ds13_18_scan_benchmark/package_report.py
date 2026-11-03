"""Package the rendered HTML and its local assets for offline reading.

The archive preserves the report's draft/complete status. It neither fetches
external resources nor follows links outside the report directory. Raw IQ and
large numerical intermediates are not copied into the presentation bundle.
"""
import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import unquote,urlsplit
import zipfile

from cohort import digest


class Links(HTMLParser):
    def __init__(self):super().__init__();self.targets=[]
    def handle_starttag(self,tag,attrs):
        self.targets.extend(v for k,v in attrs if k in ('src','href') and v)


def assets(root):
    root=root.resolve()
    parser=Links();parser.feed((root/'report.html').read_text())
    paths={root/'report.html',root/'report-receipt.json'}
    for target in parser.targets:
        uri=urlsplit(target)
        if uri.scheme or uri.netloc or not uri.path:continue
        path=(root/unquote(uri.path)).resolve()
        if not path.is_relative_to(root):raise ValueError('report link escapes presentation directory')
        paths.add(path)
    missing=[str(p.relative_to(root)) for p in paths if not p.is_file()]
    if missing:raise ValueError(f'missing report assets: {missing}')
    return sorted(paths)


def package(root,output_dir):
    root=root.resolve();paths=assets(root)
    receipt=json.loads((root/'report-receipt.json').read_text())
    if receipt['outputs']['report.html']!=digest((root/'report.html').read_bytes()):
        raise ValueError('rendered HTML differs from receipt')
    status='complete' if receipt['status']=='complete' else 'draft'
    stamp=receipt['rendered_utc'].replace(':','').replace('+','_')
    output_dir.mkdir(parents=True,exist_ok=True)
    target=output_dir/f'ds13-18-scan-report-{stamp}-{status}.zip'
    manifest=dict(status=status,rendered_utc=receipt['rendered_utc'],entrypoint='report.html',
                  scope=__doc__,files={str(p.relative_to(root)):digest(p.read_bytes()) for p in paths})
    with tempfile.NamedTemporaryFile(prefix='.report-',suffix='.zip',dir=output_dir,delete=False) as stream:
        temporary=Path(stream.name)
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for path in paths:archive.write(path,str(path.relative_to(root)))
            archive.writestr('bundle-manifest.json',json.dumps(manifest,indent=2))
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:raise ValueError('archive CRC verification failed')
            for name,expected in manifest['files'].items():
                if digest(archive.read(name))!=expected:raise ValueError('archive digest mismatch')
        # Exclusive publication: never overwrite a previous report delivery.
        os.link(temporary,target)
    finally:
        temporary.unlink()
    print(json.dumps(dict(archive=str(target),status=status,files=len(paths),bytes=target.stat().st_size)),flush=True)
    return target


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report_directory',type=Path);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();package(a.report_directory,a.output_dir)

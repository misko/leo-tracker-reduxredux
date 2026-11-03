"""Algorithm-specific command adapters; paths and identities are explicit inputs."""

TRACKERS = ('rolling', 'kalman-v2', 'linking-v2', 'coarse-seeded', 'rolling-backfill')


def tracker_stages(name, executable, observations, *, seed_executable=None):
    if name not in TRACKERS:
        raise ValueError(f'unknown tracker: {name}')
    common = {'format':'tracks-tsv-v1', 'observations':observations, 'timeout_s':90}
    stages = []
    args = ['@'+observations]
    if name == 'coarse-seeded':
        if seed_executable is None:
            raise ValueError('coarse-seeded requires a seed executable')
        stages.append(dict(common, id='coarse-seeds', kind='seed', executable=seed_executable,
                           argv=['@'+observations, '151', '8', '512', '8', '4', '16']))
        args += ['--acceleration', '250', '--seeds', '@coarse-seeds']
    stages.append(dict(common, id=name, kind='tracking', executable=executable, argv=args))
    return stages


def glrt_stage(executable, iq, exact, control, *, rate_hz, dwell_ms=120, stride_ms=120):
    """Native CLI adapter. Window selection is explicit, not inferred from filenames."""
    return {'id':'glrt', 'kind':'detector', 'executable':executable,
        'argv':['--rate-hz',str(rate_hz),'--dwell-ms',str(dwell_ms),
                '--probe-stride-ms',str(stride_ms),'--exact-template','@'+exact,
                '--control-template','@'+control,'--input-ci16','@'+iq],
        'format':'native-glrt-json-v1', 'timeout_s':90}


def location_stage(executable, fixture, *, workers=1, search=None):
    """Existing LOC1 replay port; not an automatic track-to-location converter."""
    if workers not in (1, 2):
        raise ValueError('location CLI supports one or two workers')
    args = ['score','@'+fixture,str(workers)] if search is None else [
        'search','@'+fixture,*(str(v) for v in search),str(workers)]
    if search is not None and len(search) != 3:
        raise ValueError('search requires latitude, longitude, radius_km')
    return {'id':'location','kind':'location','executable':executable,'argv':args,
            'format':'json-v1','timeout_s':300}

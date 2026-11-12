"""Measured whole-bound adapter with explicit build and original fallback."""

import ast
import ctypes as ct
import hashlib
import inspect
import json
import subprocess
from collections import OrderedDict
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3 import hierarchical

FLAGS = ('-std=c11', '-O3', '-fPIC', '-shared', '-fno-fast-math', '-ffp-contract=off')
SOURCE = Path(__file__).with_suffix('.c')
STATUS = ('ok', 'unsupported', 'nonfinite', 'positive', 'ill_conditioned', 'memory')
ORIGINAL_SHA256 = 'c906a5992ca3428c29b5c44326264549e18dc4206653b3d6f2fd12b48638607e'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(output, *, sanitize=False):
    """Compile before any timed call; no implicit compilation in the adapter."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    flags = (*FLAGS, '-fsanitize=address', '-g') if sanitize else FLAGS
    binary = output/'native_bound.so'
    command = ['cc', *flags, str(SOURCE), '-lm', '-o', str(binary)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (output/'compiler.log').write_text(completed.stdout+completed.stderr)
    completed.check_returncode()
    version = subprocess.run(['cc', '--version'], capture_output=True, text=True,
                             check=True, timeout=5).stdout
    metadata = dict(command=command, flags=flags, compiler_version=version,
        binary=str(binary.resolve()), binary_sha256=digest(binary),
        source=str(SOURCE.resolve()), source_sha256=digest(SOURCE),
        wrapper=str(Path(__file__).resolve()), wrapper_sha256=digest(__file__),
        sanitized=sanitize, ABI='SciPy LAPACKE LP64; C int32/char ABI; column-major=102')
    (output/'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
    return binary


def _original_boundaries():
    if digest(hierarchical.__file__) != ORIGINAL_SHA256:
        raise ValueError('Original hierarchical source differs from qualified boundaries')
    tree = ast.parse(inspect.getsource(hierarchical.hierarchical_bound))
    function = tree.body[0]
    boundary = next(i for i,n in enumerate(function.body) if isinstance(n, ast.Assign)
                    and ast.unparse(n.targets[0]) == 'blocks')
    finish = next(i for i,n in enumerate(function.body) if isinstance(n, ast.Assign)
                  and ast.unparse(n.targets[0]) == 'native' and
                  ast.unparse(n.value) == 'y - u @ coefficient')
    validation = ast.parse(inspect.getsource(hierarchical.hierarchical_bound))
    validation.body[0].name = '_validate'
    validation.body[0].body = validation.body[0].body[:boundary]+ast.parse('return locals()').body
    tail = ast.parse('''
def _finish(d, coefficient, native, weight, precision, v, volume, updates, change):
    pass
''')
    names = ('s','power','g','rate','beta0','alpha','pa0','v0','alpha0','counts','pa','dimensions')
    unpack = ast.parse('\n'.join(f"{name} = d[{name!r}]" for name in names)).body
    tail.body[0].body = unpack+function.body[finish+1:]

    class Metadata(ast.NodeTransformer):
        def visit_Call(self,node):
            if ast.unparse(node) == 'len(history)':
                return ast.Name(id='updates',ctx=ast.Load())
            return self.generic_visit(node)

        def visit_Subscript(self,node):
            if ast.unparse(node) == 'history[-1]':
                return ast.Name(id='change',ctx=ast.Load())
            return self.generic_visit(node)

    tail = Metadata().visit(tail)
    scope = dict(vars(hierarchical))
    for code in (validation,tail):
        exec(compile(ast.fix_missing_locations(code), '<native-bound-original-boundaries>', 'exec'),
             scope)
    return scope['_validate'],scope['_finish']


_VALIDATE, _FINISH = _original_boundaries()


def provider():
    matches = sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
                      if '/scipy.libs/' in line and 'openblas' in line.lower()})
    if len(matches) != 1:
        raise ValueError('Exactly one loaded SciPy OpenBLAS provider required')
    path = Path(matches[0])
    library = ct.CDLL(str(path))
    config = library.scipy_openblas_get_config
    config.restype = ct.c_char_p
    text = config().decode('ascii')
    threads = library.scipy_openblas_get_num_threads
    threads.restype = ct.c_int
    if 'USE64BITINT' in text or threads() != 1 or ct.sizeof(ct.c_int32) != 4:
        raise ValueError('Single-thread SciPy LP64 provider required')
    names = ('dpotrf','dpotrs','dpotri','dpocon')
    functions = [getattr(library,'scipy_LAPACKE_'+name) for name in names]
    functions[0].argtypes = [ct.c_int32,ct.c_char,ct.c_int32,ct.c_void_p,ct.c_int32]
    functions[1].argtypes = [ct.c_int32,ct.c_char,ct.c_int32,ct.c_int32,ct.c_void_p,
                            ct.c_int32,ct.c_void_p,ct.c_int32]
    functions[2].argtypes = functions[0].argtypes
    functions[3].argtypes = [ct.c_int32,ct.c_char,ct.c_int32,ct.c_void_p,ct.c_int32,
                            ct.c_double,ct.c_void_p]
    for function in functions:
        function.restype = ct.c_int32
    return library,functions,dict(path=str(path),sha256=digest(path),configuration=text,
        threads=threads(),integer_bytes=4,symbols=['scipy_LAPACKE_'+name for name in names])


def pointer(array):
    return ct.c_void_p(array.ctypes.data)


class NativeBound:
    """Validate/copy/setup/update/finish in each measured call; symbolic-only LRU."""

    def __init__(self, binary, *, cache_entries=4, min_rcond=1e-12):
        if type(cache_entries) is not int or not 0 <= cache_entries <= 8 or (
                not 1e-12 <= min_rcond <= 1):
            raise ValueError('Integer cache size0..8 and guarded reciprocal condition required')
        self.binary = Path(binary)
        self.original = hierarchical.hierarchical_bound
        self.manifest = json.loads((self.binary.parent/'manifest.json').read_text())
        if digest(self.binary) != self.manifest['binary_sha256']:
            raise ValueError('Native binary differs from build manifest')
        self.library = ct.CDLL(str(self.binary))
        self.provider,self.functions,self.provider_info = provider()
        self.addresses = [ct.cast(f,ct.c_void_p) for f in self.functions]
        self.layout = self.library.nb_layout
        self.layout.argtypes = [ct.c_int]*3+[ct.c_void_p]*2+[ct.POINTER(ct.c_int)]
        self.layout.restype = ct.c_void_p
        self.free = self.library.nb_free
        self.free.argtypes,self.free.restype = [ct.c_void_p],None
        self.run = self.library.nb_run
        self.run.argtypes = ([ct.c_void_p]*5+[ct.c_void_p]*6+[ct.c_int]+[ct.c_void_p]*2+
                            [ct.c_double]*3+[ct.c_int,ct.c_double]+[ct.c_void_p]*8)
        self.run.restype = ct.c_int
        self.cache,self.cache_entries,self.min_rcond = OrderedDict(),cache_entries,min_rcond
        self.counts = dict(calls=0,activated=0,cache_hits=0,cache_misses=0,
            **{'fallback_'+name:0 for name in STATUS[1:]})

    def clear(self):
        for value in self.cache.values():
            self.free(value)
        self.cache.clear()

    def __call__(self,*args,**kwargs):
        self.counts['calls'] += 1
        data = _VALIDATE(*args,**kwargs)
        n,p,k,t = len(data['y']),data['width'],len(data['counts']),len(data['pa'])
        if (type(data['iterations']) is not int or data['iterations']>np.iinfo(np.int32).max or
                n>100000 or p>512 or k>2048):
            self.counts['fallback_unsupported'] += 1
            return self.original(*args,**kwargs)
        y,u,s = [np.ascontiguousarray(data[name],dtype=np.float64) for name in ('y','u','s')]
        g,prior = [np.ascontiguousarray(data[name],dtype=np.int64) for name in ('g','prior')]
        power,alpha,pa = [np.ascontiguousarray(data[name],dtype=np.float64)
                          for name in ('power','alpha','pa')]
        key = (u.shape,np.packbits(u!=0,bitorder='little').tobytes(),g.tobytes())
        owned = False
        if key in self.cache:
            self.counts['cache_hits'] += 1
            layout = self.cache.pop(key)
            self.cache[key] = layout
        else:
            self.counts['cache_misses'] += 1
            code = ct.c_int()
            layout = self.layout(n,p,k,pointer(g),pointer(u),ct.byref(code))
            if not layout:
                self.counts['fallback_'+STATUS[code.value]] += 1
                return self.original(*args,**kwargs)
            if self.cache_entries:
                self.cache[key] = layout
                if len(self.cache)>self.cache_entries:
                    self.free(self.cache.popitem(last=False)[1])
            else:
                owned = True
        coefficient,native,weight,precision,v = [np.empty(z) for z in (p,n,k,p,t)]
        scalars,rate = np.empty(2),np.empty(k)
        updates = ct.c_int()
        try:
            code = self.run(layout,*self.addresses,*(pointer(a) for a in
                (y,u,s,g,power,prior)),t,pointer(alpha),pointer(pa),data['beta0'],data['pb0'],
                data['v0'],data['iterations'],self.min_rcond,*(pointer(a) for a in
                (coefficient,native,weight,precision,v,scalars)),ct.byref(updates),pointer(rate))
        finally:
            if owned:
                self.free(layout)
        if code:
            self.counts['fallback_'+STATUS[code]] += 1
            return self.original(*args,**kwargs)
        data['rate'] = rate
        result = _FINISH(data,coefficient,native,weight,precision,v,float(scalars[0]),
                         updates.value,float(scalars[1]))
        if not all(np.isfinite(np.asarray(value)).all() for value in result.values()):
            self.counts['fallback_nonfinite'] += 1
            return self.original(*args,**kwargs)
        self.counts['activated'] += 1
        return result

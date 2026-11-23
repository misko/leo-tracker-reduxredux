"""Defer one reviewed benchmark import until the installed detector is called."""

import ast
from contextlib import contextmanager
from hashlib import sha256
from importlib import import_module
from importlib.machinery import PathFinder, SourceFileLoader
from pathlib import Path
import sys


class DetectorLoader:
    def __init__(self, code, receiver, audit):
        self.code, self.receiver, self.audit = code, receiver, audit

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        receiver, audit = self.receiver, self.audit

        def detector(*args, **kwargs):
            original = import_module(receiver).detector
            audit["original_calls"] += 1
            return original(*args, **kwargs)

        module.detector = detector
        exec(self.code, vars(module))
        audit["deferred"] = True


class DetectorFinder:
    def __init__(self, scanner, receiver, source, source_sha, receiver_source, receiver_sha, audit):
        self.scanner, self.receiver, self.source, self.source_sha = scanner, receiver, source, source_sha
        self.receiver_source, self.receiver_sha, self.audit = receiver_source, receiver_sha, audit

    def find_spec(self, name, path, target=None):
        if name != self.scanner or target is not None:
            return None
        if self.receiver in sys.modules:
            self.audit["fallback"] = "receiver already loaded"
            return None
        spec = PathFinder.find_spec(name, path, target)
        if (spec is None or spec.origin is None or Path(spec.origin).resolve() != self.source
                or type(spec.loader) is not SourceFileLoader):
            self.audit["fallback"] = "unsupported scanner origin or loader"
            return None
        try:
            source = self.source.read_bytes()
            reference = self.receiver_source.read_bytes()
            if sha256(source).hexdigest() != self.source_sha or sha256(reference).hexdigest() != self.receiver_sha:
                raise ValueError("unreviewed scanner or receiver source")
            tree = ast.parse(source, filename=str(self.source))
            matches = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.level == 0
                       and node.module == self.receiver and [(a.name, a.asname) for a in node.names] == [("detector", None)]]
            if len(matches) != 1:
                raise ValueError("unsupported detector import")
            tree.body.remove(matches[0])
            code = compile(tree, str(self.source), "exec", dont_inherit=True)
        except (OSError, SyntaxError, ValueError) as exc:
            self.audit["fallback"] = str(exc)
            return None
        spec.loader = DetectorLoader(code, self.receiver, self.audit)
        return spec


@contextmanager
def defer_detector(*, enabled, audit):
    if not enabled:
        yield
        return
    import empty_bootstrap as staged

    audit.update(deferred=False, original_calls=0)
    scanner, receiver = (name.removesuffix(".py").replace("/", ".") for name in (staged.SCANNER, staged.RECEIVER))
    if scanner in sys.modules:
        audit["fallback"] = "scanner already loaded"
        yield
        return
    finder = DetectorFinder(scanner, receiver, staged.PAYLOAD / staged.SCANNER, staged.EXTRA_SOURCES[staged.SCANNER],
                            staged.PAYLOAD / staged.RECEIVER, staged.EXTRA_SOURCES[staged.RECEIVER], audit)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)

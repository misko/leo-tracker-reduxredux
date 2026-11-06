def pack(value, pngs):
    if set(pngs) != set(PLOTS):
        raise ValueError("All eight PNGs required in standalone evidence")
    blobs = {}

    def encode(v):
        if isinstance(v, np.generic) and v.dtype.fields is None and v.dtype.subdtype is None:
            a = np.asarray(v)
            if a.dtype.hasobject:
                raise ValueError("Object scalars cannot be persisted as scientific evidence")
            return ["scalar", a.dtype.str, a.tobytes().hex()]
        if isinstance(v, (np.ndarray, np.generic)):
            a = np.asarray(v)
            if a.dtype.hasobject:
                raise ValueError("Object arrays cannot be persisted as scientific evidence")
            stream = io.BytesIO()
            np.save(stream, a, allow_pickle=False)
            raw = stream.getvalue()
            sha = sha256_digest(raw)
            blobs.setdefault(sha, raw)
            return ["array" if isinstance(v, np.ndarray) else "scalar", sha]
        if is_dataclass(v) and not isinstance(v, type):
            v = {f.name: getattr(v, f.name) for f in fields(v)}
        if isinstance(v, dict):
            return ["map", [[encode(k), encode(item)] for k, item in v.items()]]
        if isinstance(v, (tuple, list)):
            return ["tuple" if isinstance(v, tuple) else "list", [encode(item) for item in v]]
        if isinstance(v, float):
            return ["float", v.hex()]
        if v is None or type(v) in (bool, int, str):
            return v
        raise TypeError("Unsupported scientific evidence type: " + type(v).__name__)

    tree = encode(value)
    figures = {}
    for name in PLOTS:
        data = pngs[name]
        if not isinstance(data, bytes) or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("PNG bytes required")
        sha = sha256_digest(data)
        blobs.setdefault(sha, data)
        figures[name] = sha
    header = canonical_json_bytes(dict(schema_version=1, tree=tree, figures=figures))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:

        def write(name, raw, compression):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = compression
            archive.writestr(item, raw, compresslevel=1)

        write("values.json", header, zipfile.ZIP_DEFLATED)
        for sha, raw in sorted(blobs.items()):
            write(sha.split(":", 1)[1], raw, zipfile.ZIP_STORED)
    return output.getvalue()

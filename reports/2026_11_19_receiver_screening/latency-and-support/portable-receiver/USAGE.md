# Portable saved-recording receiver

This bundle runs the stock wide detector and the compact phase-release position receiver on x86-64 Linux. The tested runtime uses CPython 3.12, the Python libraries in requirements.txt, and the system libfftw3.so.3. The native solver verifies the qualified SciPy LP64 provider bytes when it starts. Use the matching Linux SciPy wheel pinned in requirements.txt.

Prepare a local Python environment from a wheel directory and invoke the bundle from any working directory.

```sh
python3.12 -m venv /path/to/receiver-env
/path/to/receiver-env/bin/python -m pip install --no-index --find-links /path/to/wheels \
  -r /path/to/portable-receiver/requirements.txt
/path/to/receiver-env/bin/python -IB /path/to/portable-receiver/receive.py \
  /path/to/my-input.json --out /path/to/new-results
```

Use example-input.json as a template. List the complete segment manifests in physical order. Each segment directory contains the original manifest, index and compressed acquisition chunks. Provide a bare lowercase SHA-256 for every segment manifest and the track configuration. The causal TLE object names each TLE file relative to the named archive root and supplies its SHA-256. Preserve the archive structure and snapshot filenames, which carry retrieval times and content digests. Relative file paths resolve from my-input.json. The supplied offer sets the center and width in kilometers. Use the original screening center for a matched result.

The supported format is a complete dual-receiver, 20 ms, 10 MS/s CI16 short-window v2 capture containing at least two saved segments. The input has one consistent radio, generation and pilot edge. Two distinct CPUs run the detector by segment, and the first CPU runs the position fit. Pass `--cpus 4 5` to choose CPUs and `--raw-deadline 360` to set the raw replay limit in seconds. The new output directory contains position.json, the authenticated native factor document and raw and position receipts. Both c = 0 and fitted-c arms are returned in position.json. Provide normal read permissions for the input and write permissions for the separate output.

# Pre-worker environment snapshot failure

The first launcher invocation (terminal session86062) exited1 while reading the
installed `leo.storage.scanner_tracking_source` module to archive its bytes:

```
PermissionError: [Errno 13] Permission denied: '/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/lib/python3.14/site-packages/leo/storage/scanner_tracking_source.py'
```

No dataset worker, observation export, bank generation or validation had begun.
The exact launcher is preserved as `launch-before-read-fix.py`. The active
launcher now reads the known installed module paths using `sudo -n cat` and
still checks their bytes against the environment hashes. No installed file
or permission was changed. This is bootstrap repair, not a scientific-stage
retry or a change to the frozen data/model protocol.

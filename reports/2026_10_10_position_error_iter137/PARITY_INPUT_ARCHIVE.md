# Selected inference input archive

`parity-inputs.tar.gz` contains exactly 193 selected-state projections and 193 clean inference documents. The original files remain local. `PARITY_INPUT_ARCHIVE.json` binds every member's byte length and SHA256 plus the archive hash. A fresh temporary-directory restore passed all 386 file checks.

Archive: 10,955,246 bytes. SHA256: `2f2eead7fcc70c523f4f51a6f539c3d5b18bb90e3f2ec2d970672cc0f3bec2eb`.

Restore through `archive_inputs.restore(archive_path, manifest, destination)` rather than unrestricted tar extraction. The helper rejects unsafe paths, duplicate or unbound members, hash mismatches, and differing existing files. Identical existing files are verified and retained. Restore into this report directory to satisfy parity-bindings.json paths. No recording inputs, reference values, or model results are regenerated.

This is a preparation archive, not a numerical protocol or parity result. The unpublished parity freezer must still be reviewed and explicitly invoked before any recording reconstruction.

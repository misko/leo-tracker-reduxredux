# Raw measurement-sensitivity receipts

`results.tar.gz` contains all twelve terminal member receipts and twelve exclusive claims. Failed or unqualified attempts would remain in their original receipts; this run contains 72 qualified fits. Raw local JSON originals remain untouched.

Archive SHA256: `c7720295e05a41796fdcb6fde13355449ae66166857076a3437d7a4a74e8186f`; compressed size 7,017,501 bytes. `RESULT_ARCHIVE.json` binds every path, byte count and SHA256 plus the numerical protocol. The helper checked all frozen source/input bindings, exact member/claim identity, terminal coverage and full archive readback before writing the manifest.

For review, inspect `RESULT_ARCHIVE.json` and list with `tar -tzf results.tar.gz`. Extract into a new empty directory with `tar -xzf results.tar.gz -C /path/to/empty-directory`; paths are only `results/*.json`. Verify extracted byte counts and hashes against the manifest before use. Do not overwrite existing research receipts.

The archive supports reproduction of the report without new fits. It does not imply an accuracy improvement, operational deployment recommendation or independent validation.

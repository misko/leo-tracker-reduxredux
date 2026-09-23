# Post-run prior provenance supplement

This is a post-run, non-numerical provenance supplement. It does not claim a
pre-execution binding and does not change or regenerate `frozen-prior.json`.

- frozen prior: `sha256:aced18dfb3b235097e0d648dbb911aeb6ba4519b365b166aafc8ca095a847ed6`
- executed learner: `sha256:24e0af6c25688635ee9b64bd144822b9cef0b77a470b5d07f625528acc2aeb44`
- original learner: `sha256:bac4742720aca1c8af020d914189db4e6ccd73c812cb0578db4c6d0a5daf45fb`
- orbit update modes: `sha256:979c929ae231a48bee54e10e9fafab28a198c49d8e9afbcda2ba25f9ac5b40b2`
- propagation parser: `sha256:238f45112bacd3b14b37f296fb17f056d66a860e469363cca44d876514ac544f`
- archive reader: `sha256:4197f5e8cbbe43018df88318872746dfbec253aac1285a7971290c7439024da1`
- frame conversion: `sha256:b6c98c11d25957c8f535d09a4f4cc47f3f82745b63ca57c61f9e8d5949fbb8e0`

`src/leo/sky/frames.py` had no worktree diff after execution. Its last commit is
`65ec1f5a908fb38de561473adce0604661e7edb5` dated 2026-08-20, before this
run. This closes the discovered transitive `raw_state` frame-conversion source
binding with transparent post-run evidence; the numerical output is unchanged.

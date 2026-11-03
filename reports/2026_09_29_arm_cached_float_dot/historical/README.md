# Historical pre-rebase source recovery

`old-b719-sources/` is the reconstructed source snapshot for the original host704 build receipt `b71972215ad0e822beba729714e8acdfc92ce781402bdcbd0cf0cd13b0da8bca` and the original ARM unit receipt `04e540da90e67271ceb696bb487520bbb7bab174544de976f9db09ab83109055`.

`old-b719-source-verification.json` checks every one of the 56 source files named by `host704/build-receipt.json`. All expected and reconstructed SHA-256 values match, including historical `full_search.c` SHA-256 `80150c111d1562f20c0d308d243d40b053811eaf06a7142ff93ef24934015f9c`.

This directory contains sources only. It does not replace or modify the current sealed `sources/` or `builds/` trees. The original host704 and ARM-unit evidence remains historical evidence for its own receipt; the final speed decision uses the later NEON-moments-v2 build and cohorts documented in `qualification.md`.

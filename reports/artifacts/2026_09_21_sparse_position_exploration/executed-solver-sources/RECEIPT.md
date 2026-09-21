# Executed sparse-solver source receipt

The Gaussian contrast and Laplace contrast solver snapshots match the hashes
embedded in their sealed benchmark results:

| Variant | Executed solver SHA-256 | Formatted working solver SHA-256 |
|---|---|---|
| Gaussian offset contrast + MAP rates | `c34da8f1387869c7de48365280d22f7efecc852bafdc1d3259b894f92af85436` | `75449ab832c63222147c3825eaf507bc253969beb7b6213f0223b6d5d662cfc5` |
| Gaussian contrast + GN-Laplace rates | `7fa01994cf9c5588121d659d3177aa5c23d23438505c36ac7dec611c4611895e` | `66e05e071961154782e369e7f2eca534d6727783bf3d19c6cee6ed4db5796cf1` |
| Stabilized Student-t | `38ff6ff4fb76e0ce96917a8a55346a072c0ca192129788a8c22dc5a38751cd4c` | `9688d431183a3922145d24ca3f09c04e47e896307360367bd44636af28cf8d8c` |

The exact stabilized Student-t source at hash `38ff6f...` was not retained
before diagnostic trace fields were added. The included
`sparse_orbit_solver.post_execution_diagnostics.py.txt` is explicitly a later
version and must not be represented as the executed source.

Benchmark runner snapshots were taken before formatting:

| Runner | Executed snapshot SHA-256 | Formatted working SHA-256 |
|---|---|---|
| Stabilized Student-t | `57024daa5bc6247a5b8c9e141dba2067f1b451f3120f4981bba5ccff0fc3a2ed` | `335a073c3610cf828ff09ee97787c89e13fd3889d46b0edad55d5b0d1c2ee4b4` |
| Gaussian offset contrast | `d9bf707c838b150cb270c760b04682eb8b2aecd63381d5711d7b7e325b86031b` | `e46609a04ba7d21d05dd99fe9c8a4ce4dbe1d170b152983214d09561f2112c73` |
| GN-Laplace contrast | `3a272f99b4bfd18416f8de64af36ba462f6c26ba097ca9a16b630c6e7851ca4e` | `6c229672c921e7cd09ec38834aecf534e5782c785741e1c345dc80cdd2787b57` |

The working-source differences are Ruff import cleanup and line wrapping only;
no numerical behavior changed.

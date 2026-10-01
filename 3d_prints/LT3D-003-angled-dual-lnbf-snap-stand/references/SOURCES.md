# Downloaded LNB CAD references

Downloaded 2026-09-30 from Norsat's manufacturer product page:
[2000 dual-band Ku-band PLL LNB](https://www.norsat.com/products/2000-dual-band-ku-band-pll-lnb-1).

| Local original | Manufacturer download | SHA-256 |
|---|---|---|
| `norsat-2000-f.step` | [F connector STEP](https://cdn.shopify.com/s/files/1/0529/5806/8919/files/3DModel-LNB_Ku_2000_F-Conn.STEP) | `e80b352d366a45754824d1553540eefe5df2ec8ee7dc4ef6730378f96ec57d2c` |
| `norsat-2000-n.step` | [N connector STEP](https://cdn.shopify.com/s/files/1/0529/5806/8919/files/3DModel-LNB_Ku_2000_N-Conn.STEP) | `f1ada53c3a3100717df84ada5075538dacb6ef991a5551d2d72617f97d46aaa8` |

These are genuine STEP files, successfully parsed into solid-containing compounds.
They are **not suitable for fitting to the existing clips**: they have a waveguide
flange interface rather than a 40 mm clamping neck. Both also fail CadQuery/OCCT's
full validity test. Their untouched bytes are retained for provenance; neither
is scaled, silently repaired, installed in the assembly, or used to claim fit.
Bounding envelopes are about 43.87 × 43.07 × 113.28 mm (F) and
43.87 × 43.07 × 118.62 mm (N). They are not Geostar or Edision models.

Manufacturer files remain third-party material; no project license is assigned
to them. These local copies are engineering references, not a publication or a
claim of redistribution rights.

The search also covered consumer LNB STEP/STP/SolidWorks files, GrabCAD, and
GitHub CAD references. GrabCAD returned HTTP 403 in this environment. No
accessible matching consumer STEP was located. The user's brand-level names
"geostar and edison" do not establish exact part numbers.

[Edision's SL-2 product page](https://www.edision.gr/en/detail/lnb-sl-2-single)
states a 40 mm mounting interface but supplies no STEP or dimensioned body
drawing. Its **package dimensions are not LNB dimensions** and were not used.
[GEOSATpro UL1PLL's vendor page](https://satelliteav.com/ul1pll) was checked as
a possible interpretation of Geostar, not as an identification of the installed
hardware. No compatible STEP was found there either.

The separate `../envelopes/ASSUMED-*.step` files are locally generated
clearance scenarios. They are **not downloaded manufacturer models**. Every
dimension beyond the user-confirmed neck class is explicitly an assumption.

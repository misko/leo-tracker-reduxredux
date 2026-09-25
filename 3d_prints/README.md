# Printable parts

This directory contains project-owned, reproducible 3D-printable hardware.
Each design has a stable family ID and a self-contained directory containing
its source, generated STL files, design record, and mesh tests. Generated STL
files are checked in intentionally: they are the immediately printable release
artifacts; their generators are the source of truth.

| Design family | Purpose | Directory |
| --- | --- | --- |
| `LT3D-001` | Free-standing, dual-LNBF holder | [`LT3D-001-dual-lnbf-stand`](LT3D-001-dual-lnbf-stand/) |
| `LT3D-002` | Vertical, snap-in dual-LNBF holder | [`LT3D-002-dual-lnbf-snap-stand`](LT3D-002-dual-lnbf-snap-stand/) |

Never alter a released part identifier's geometry in place. Create the next
revision (for example, `LT3D-002`) when a material geometry or fit contract
changes.

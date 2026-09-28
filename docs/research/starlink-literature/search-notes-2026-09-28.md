# Search and access notes — 2026-09-28

## Method

Located the established literature archive through repository file/content
search. Preserved its original review, IDs, manifests, PDFs, datasets, and
unrelated workspace edits. Expanded from the existing Ku-band/PNT bibliography
using public web search, author publication lists, primary publisher pages,
arXiv records, conference artifacts, and firsthand technical articles.

Primary collections consulted include UT Austin's Radionavigation Laboratory,
Ohio State's author-hosted PNT papers, arXiv, A&A, Nature/npj, ION, institutional
networking-paper repositories, Black Hat, the SDR-X author blog, and SpaceX's
public technical reports. Search-result aggregators and social posts were
discovery aids, not the scientific evidence used in summaries.

Representative executed searches (including targeted follow-ups):

- `Starlink signal structure synchronization navigation Humphreys Qin papers`
- `Starlink research survey measurement astronomy environmental impact papers 2025 2026`
- `Starlink navigation Doppler positioning 2021 2024 2025 Kassas pdf`
- `Starlink navigation maximum likelihood time arrival Doppler Qin paper`
- `Starlink network measurement survey obstruction performance 2024 2025 2026 arxiv`
- `Starlink survey research networking arxiv survey`
- `Starlink Hypatia simulator paper Kassing 2020 arxiv`
- `Starlink direct to cell measurements scheduling algorithms 2026 paper`
- `Methodologies for Understanding Starlink Scheduling Algorithms paper`
- `Starlink Doppler satellite identification ephemeris error navigation 2025 2026 pdf`
- `site.people.engineering.osu.edu "Towards Navigation with Non-Cooperative"`
- `site.people.engineering.osu.edu "Direction of Arrival" "Starlink"`
- `Starlink security terminal fault injection paper pdf blackhat Lennert Wouters`
- `site.sdr-x.github.io starlink 2026 downlink`
- `Starlink optical brightness Tyson McDowell 2020 arxiv`
- `Starlink satellite demise aluminum oxides ozone depletion 2024 paper Ferreira`
- `"SNIFFLES" arxiv`
- `"Starlink" "reversed solar" arxiv`
- `"Dissecting the StarLink" pdf`

The search cutoff is 2026-09-28. Original publication date, preprint revision,
and webpage crawl date were kept separate where recoverable. Search-engine
relative dates were not used to establish publication chronology. In particular,
X36 is 2023 work despite recent reposts, and X41's journal publication predates
its arXiv deposit.

## Inclusion and reading depth

Included primary studies directly examining Starlink, foundational methods
needed to interpret those studies, relevant comparative LEO papers, firsthand
technical articles, and a small number of operator reports. Prioritized
waveforms, pilots, QAM, timing, Doppler, identification, and receiving hardware,
then broadened across networking, D2C, security, astronomy, and environment.

The review adds X01–X42 and article snapshots A01–A10. Existing P01–P07 and
R01–R04 retain their identifiers. A01–A04 overlap the existing R01 series;
A09 overlaps R02. X02/X03 are related early papers; X05 overlaps the later
timing work; X42 reuses X19's observations. Do not count these as independent
replications. Downloads are deduplicated within the new source IDs and checked
against the existing archive by digest during validation.

Available PDFs were parsed and relevant abstract, method/result, and conclusion
passages consulted. This is a scoping review, not a formal systematic review,
meta-analysis, numerical reproduction, or complete methodological audit. PDF
text extraction is not reliable for every plotted value or diagram. Numerical
claims not checked in figures remain limited to explicit textual statements.
Entries with inaccessible PDFs are explicitly marked abstract/page only.

## Download and storage policy

- PDFs: `local/papers/Xnn-topic.pdf`, alongside existing PDFs.
- Article HTML and extracted PDF text: `local/sources/`.
- New provenance: `downloads-2026-09-28.json`; original `downloads.json` preserved.
- Public arXiv/publisher/author copies preferred. Normal alternate public
  copies were tried after failed transfers; no paywall or login was bypassed.
- PDF signature and page parsing checked before retaining a download as a PDF.
  SHA-256, bytes, page count, URL, retrieval time, and available metadata recorded.
- X26 is an article printout from a public FAA docket, explicitly distinguished
  from a publisher PDF. NASA's bibliographic record offered no download.
- HTML-only posts were saved as HTML, not passed off as original PDFs. Images
  and scripts referenced by those HTML pages are not a complete offline mirror.
- No raw IQ, large network datasets, media, or third-party executables were
  downloaded in this pass. No new RF collection or active measurement occurred.

## Access gaps and further leads

Validation completed on 2026-09-28: 35 new PDFs and 10 HTML snapshots total
162,877,077 bytes. All retained downloads match their manifest sizes and SHA-256
hashes; all 35 PDFs parse with the recorded page counts. All downloaded files
are Git-ignored. The archive now contains 45 PDFs, including the 10 pre-existing
copies, whose recorded hashes still match. No duplicate PDF digest was found
between the new and original manifests. Local links in the four edited/new
Markdown catalog documents resolve. This validates archive integrity, not the
scientific findings of the publications.

The source index is the authoritative status list. X17, X19, X20, X21, X29,
X40, and X42 have no validated local PDFs in this pass. Attempts encountered
HTTP 403/406 responses or incomplete transfers. Their primary pages/abstracts
support only the limited summaries provided. Failed-attempt history is retained
in the manifest; no malformed download is represented as a reviewed paper.

Additional leads identified but not claimed as reviewed:

- [Position and Navigation Using Starlink (Grayver et al., 2024)](https://doi.org/10.1109/AERO58975.2024.10521263):
  no verified primary full text was retrieved during this pass.
- [A Variegated Look at Direct-to-Cell Satellites in the Wild](https://doi.org/10.1145/3788086):
  newer full-stack D2C study; detailed review remains outstanding.
- [Performance Assessment of DOA and Doppler Positioning Under Erroneous Starlink and Oneweb LEO Satellites Ephemerides](https://ieeexplore.ieee.org/abstract/document/11612532/):
  relevant 2026 extension to X39, not included as a full review.
- [Towards Genuine Coexistence](https://arxiv.org/abs/2608.11659):
  2026 radio-astronomy mitigation/limit proposal related to SNIFFLES.

Coverage remains selective for gateway/E-band links, optical inter-satellite
hardware, antenna/RFIC implementation papers, complete patent families,
regulatory filings across jurisdictions, disaster/education/economic outcomes,
policy/geopolitics, non-English publications, dissertations, and general news.
These are not implied to be exhausted by the present catalog. A claim of
"all Starlink literature and articles" would require a specified database,
language, date range, and reproducible inclusion protocol, and still could not
guarantee every webpage or inaccessible publication.

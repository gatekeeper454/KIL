# Citation policy

Every KIL-authored Markdown document must link to KTP's canonical citation
metadata. `tests/test_document_citation.py` enforces this requirement for
existing and future documents.

The two original drafts under `docs/drafts/` are byte-preserved source
artifacts and are therefore exempt from in-place modification. Their enclosing
`docs/drafts/README.md` carries the citation, and their recorded SHA-256 hashes
must continue to match.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

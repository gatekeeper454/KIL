# Project-boundary reference cleanup design

## Objective

Remove the name of an unrelated external project from every current KIL project
file. Preserve useful KIL and KTP guidance by rewriting affected sentences in
KIL-only terms rather than deleting whole sections or substituting a generic
external-project label. Git history is outside scope.

## Scope

The cleanup covers the three tracked Markdown sources containing the name,
their generated `.htm` companions, and the occurrence in the maintainer's
uncommitted OTCS lineage work. It does not alter unrelated OTCS content, KTP
semantics, historical commits, or third-party dependencies and caches.

## Publication and synchronization

Markdown remains the source of record. After the source rewrites and required
lineage entry, regenerate the complete tracked reader corpus so every changed
`.md` file has a fresh same-directory, self-contained `.htm` partner. Commit
only the cleanup artifacts on an isolated branch, fast-forward `main`, restore
the maintainer's uncommitted OTCS work, apply the same narrow cleanup to its
lineage occurrence, and push `main`.

## Verification

A case-insensitive search of current project-owned files must return no matches
for the removed name. The generated-reader check must prove exact Markdown/HTML
pairing and freshness, the full repository validation must pass, and local
`main`, `origin/main`, and the remote branch head must resolve to the same
cleanup commit. The uncommitted OTCS files must remain uncommitted and otherwise
preserved.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

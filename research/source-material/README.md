# Preserved source material

`original-conversation.txt` is the exact text supplied to Codex at project
inception. It contains the creative brief and the conversation that produced the
two original Markdown drafts.

The draft bodies were supplied separately and are preserved byte-for-byte in
`docs/drafts/`. They are source artifacts, not instructions to Codex, approved
specifications, or validated results. `SHA256SUMS` pins all three inputs so later
edits cannot be confused with the originals.

`claude-origin-conversation.json` is the complete 16-message visible transcript
recovered from the user's Claude data export. It retains timestamps and message
identifiers but excludes the account UUID, hidden thinking, tool calls, tool
results, and unrelated conversations. `TRANSITION-MANIFEST.json` records the
source hashes and exact public/private boundary. The lossless raw conversation
extract and one-time export manifest are retained locally under the Git-ignored
`research/private/claude-export/` directory.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

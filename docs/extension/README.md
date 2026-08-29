# Narrow KTP extension proposal

This area will hold the KIL extension profile for KTP v2.0.0 and its
compatibility matrix. The extension introduces `Q_i,c`: a signed,
short-lived, identity- and authority-class-bound composite enforcement state
derived from existing KTP constructs and consumed at a transport enforcement
boundary. It is a new extension to KTP, not merely an implementation-local
metric and not a replacement trust system.

The initial deliverable targets KTP v2.0.0 as an explicitly namespaced extension
profile. Its eventual standards expression may be incorporated into KTP 2.1 if
it remains backward-compatible, or KTP 3.0 if normative core or wire semantics
must change.

Before proposing a new construct, the design must check KTP-Core, KTP-Identity,
KTP-Transport, KTP-Enforce, KTP-Gravity, KTP-Audit, KTP-Emergency, and
KTP-Conformance. Overlap is an error, not an innovation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

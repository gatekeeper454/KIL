"""Verifier-owned finite image membership for the accepted V3B2 workload.

Target references are pinned by the accepted V3B1 public manifest commitment.
Distinct config identities follow the independently verified archive/native
registry chains recorded in the plan's 'Verified native image identity chains':
docs/superpowers/plans/2026-09-06-v3b2a-kind-calico-nominal.md.

This proves ONLY membership in that finite contract, not observed CRI aliases,
node-store provenance, runtime container identity, or readiness. In particular,
admitting either KIL ImageRef here does not establish which alias branch a node
actually used. NodeImageReferenceProof remains the separate observation proof.
There is no caller-supplied acceptance table or override.
"""
from dataclasses import dataclass


ACCEPTED_MANIFEST_SHA256 = 'fa39212f1ffad95a1b5a674021ac5ce4ed9458025ce0dcc80077070355141cd0'
_KIL_TARGET = 'sha256:45a167d79b92f352af05a3e9cb8a9df8e972e38ab23d04ca692053e2eaf63649'
_KIL_CONFIG = 'sha256:f21285be21c8f691b9b60b7e38bb309564a5cc238512c7455eb7759f4d922ddb'
_ENVOY_TARGET = 'sha256:57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4'
_ENVOY_CONFIG = 'sha256:ef846ec85aabf01a2ff7176a185260e476ca43d20478f57281d88f7a66d5671f'
_KIL_REQUEST = 'kil.local/kil-v3b2:sha256-' + _KIL_TARGET[7:]
_ENVOY_REQUEST = 'docker.io/envoyproxy/envoy@' + _ENVOY_TARGET
_CONTRACT = (
    ('kil', _KIL_REQUEST, _KIL_TARGET, _KIL_CONFIG,
     (_KIL_CONFIG, 'kil.local/kil-v3b2@' + _KIL_TARGET)),
    ('envoy', _ENVOY_REQUEST, _ENVOY_TARGET, _ENVOY_CONFIG, (_ENVOY_REQUEST,)),
)


class AcceptedImageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AcceptedImage:
    role: str
    requested_image: str
    target_digest: str
    config_digest: str
    image_refs: tuple[str, ...]

    def __post_init__(self):
        values = (self.role, self.requested_image, self.target_digest, self.config_digest)
        if (any(type(value) is not str or len(value) > 256 for value in values)
                or type(self.image_refs) is not tuple or len(self.image_refs) not in (1, 2)
                or any(type(value) is not str or len(value) > 256 for value in self.image_refs)):
            raise AcceptedImageError('accepted image descriptor types/bounds are not exact')
        if (*values, self.image_refs) not in _CONTRACT:
            raise AcceptedImageError('descriptor is not a verifier-owned accepted image')


ACCEPTED_IMAGES = tuple(AcceptedImage(*row) for row in _CONTRACT)


def validate_accepted_image(role: str, requested_image: str, image_ref: str) -> None:
    """Reject nonmembers; success asserts finite membership only, not provenance."""
    if any(type(value) is not str or len(value) > 256 for value in (role, requested_image, image_ref)):
        raise AcceptedImageError('image membership inputs must be exact bounded strings')
    if not any(role == row[0] and requested_image == row[1] and image_ref in row[4]
               for row in _CONTRACT):
        raise AcceptedImageError('image pair is outside the verifier-owned accepted contract')


__all__ = ('ACCEPTED_MANIFEST_SHA256', 'ACCEPTED_IMAGES', 'AcceptedImage',
           'AcceptedImageError', 'validate_accepted_image')

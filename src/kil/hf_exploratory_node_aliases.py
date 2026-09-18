"""Finite accepted-config associations for owned-node alias repair only."""
from dataclasses import dataclass
from datetime import date
import json
import re
from kil.v3b2_accepted_images import ACCEPTED_IMAGES
from kil.v3b2_node_image_references import _node_rows, _closed, _pairs, _reject_number, _decimal, _text


def accepted_image(role):
    if type(role) is not str or role not in ('kil','envoy'):
        raise ValueError('node_alias_role_not_accepted')
    return next(row for row in ACCEPTED_IMAGES if row.role == role)


def canonical_alias(image):
    return 'kil.local/kil-v3b2@'+image.target_digest if image.role == 'kil' else image.requested_image


def validate_import_ref(reference):
    if type(reference) is not str:
        raise ValueError('node_alias_import_ref_not_exact')
    match = re.fullmatch(r'import-([0-9]{4}-[0-9]{2}-[0-9]{2})@(sha256:[0-9a-f]{64})',reference)
    if match is None: raise ValueError('node_alias_import_ref_not_exact')
    date.fromisoformat(match[1])
    return match[2]


def complete_row(row, target, media):
    if row is None: raise ValueError('node_alias_target_row_missing')
    counts = re.fullmatch(r'\(([1-9][0-9]{0,9})/([1-9][0-9]{0,9})\)',row[4])
    if (row[1] != media or row[2] != target or row[3] != 'complete' or counts is None
            or counts[1] != counts[2] or re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',row[5]) is None
            or row[6] not in {'B','KiB','MiB','GiB','TiB','PiB','EiB'} or row[7] != 'true'):
        raise ValueError('node_alias_target_content_not_complete')
    return row


@dataclass(frozen=True)
class AliasState:
    config_row: tuple
    canonical_present: bool
    canonical_reported: bool
    import_rows: tuple


def analyse_aliases(table, inspection, role):
    image = accepted_image(role)
    if type(table) is not bytes or len(table)>262144 or type(inspection) is not bytes or len(inspection)>16384:
        raise ValueError('node_alias_observation_bound')
    rows = _node_rows(table)
    document = json.loads(inspection,object_pairs_hook=_pairs,parse_int=_reject_number,
                          parse_float=_reject_number,parse_constant=_reject_number)
    status = _closed(document,frozenset({'status'}))['status']
    if type(status) is not dict: raise ValueError('node_alias_quiet_status_not_exact')
    keys = frozenset({'id','repoTags','repoDigests','size','username','pinned'})
    _closed(status,keys|({'uid'} if 'uid' in status else set()))
    if status['id'] != image.config_digest: raise ValueError('node_alias_cri_config_not_accepted')
    _decimal(status['size'],positive=True); _text(status['username'],'username',256,empty=True)
    if type(status['pinned']) is not bool: raise ValueError('node_alias_pinned_not_bool')
    if 'uid' in status:
        _decimal(_closed(status['uid'],frozenset({'value'}))['value'],signed=True)
        if status['username']: raise ValueError('node_alias_uid_username_conflict')
    for field in ('repoTags','repoDigests'):
        values = status[field]
        if (type(values) is not list or len(values)>8 or any(type(value) is not str for value in values)
                or len(set(values)) != len(values)):
            raise ValueError('node_alias_refs_not_bounded_unique')
        for value in values: _text(value,'node alias',512)
    if status['repoTags'] != ([image.requested_image] if role == 'kil' else []):
        raise ValueError('node_alias_foreign_repo_tag')
    media = 'application/vnd.oci.image.'+('manifest' if role == 'kil' else 'index')+'.v1+json'
    config = complete_row(rows.get(image.config_digest),image.target_digest,media)
    if role == 'kil': complete_row(rows.get(image.requested_image),image.target_digest,media)
    canonical = canonical_alias(image)
    present = canonical in rows
    if present: complete_row(rows[canonical],image.target_digest,media)
    imported = []
    for reference in status['repoDigests']:
        if reference == canonical:
            if not present: raise ValueError('node_alias_cri_canonical_not_in_table')
            continue
        prefix = 'docker.io/library/'
        if not reference.startswith(prefix): raise ValueError('node_alias_foreign_repo_digest')
        name = reference[len(prefix):]
        digest = validate_import_ref(name)
        row_media = media if digest == image.target_digest else 'application/vnd.oci.image.index.v1+json'
        imported.append(complete_row(rows.get(name),digest,row_media))
    return AliasState(config,present,canonical in status['repoDigests'],tuple(sorted(imported)))

"""Finite node alias fixture proofs; no native execution."""
from copy import deepcopy
import importlib
import importlib.util
import json
import unittest
from kil.v3b2_accepted_images import ACCEPTED_IMAGES


def fixture(role='kil', canonical=False):
    image = next(row for row in ACCEPTED_IMAGES if row.role == role)
    media = 'application/vnd.oci.image.'+('manifest' if role == 'kil' else 'index')+'.v1+json'
    wrapper = 'sha256:'+('a' if role == 'kil' else 'b')*64
    imported = 'import-2026-09-18@'+wrapper
    target = 'kil.local/kil-v3b2@'+image.target_digest if role == 'kil' else image.requested_image
    rows = ['REF TYPE DIGEST STATUS SIZE UNPACKED',
            f'{image.config_digest} {media} {image.target_digest} complete (7/7) 46.4 MiB true',
            f'{imported} application/vnd.oci.image.index.v1+json {wrapper} complete (7/7) 46.4 MiB true']
    if role == 'kil': rows.append(f'{image.requested_image} {media} {image.target_digest} complete (7/7) 46.4 MiB true')
    if canonical: rows.append(f'{target} {media} {image.target_digest} complete (7/7) 46.4 MiB true')
    status = {'id':image.config_digest,'repoTags':[image.requested_image] if role == 'kil' else [],
              'repoDigests':['docker.io/library/'+imported]+([target] if canonical else []),
              'size':'48635509','username':'','pinned':False}
    return image, imported, ('\n'.join(rows)+'\n').encode(), {'status':status}


class NodeAliasesTests(unittest.TestCase):
    def analyse(self, table, status, role):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_node_aliases'),'finite alias proof helper is missing')
        return importlib.import_module('kil.hf_exploratory_node_aliases').analyse_aliases(table,json.dumps(status).encode(),role)

    def test_exact_config_target_and_cri_association_bind_generated_wrapper(self):
        for role in ['kil','envoy']:
            with self.subTest(role=role):
                image, imported, table, status = fixture(role)
                state = self.analyse(table,status,role)
                self.assertEqual(state.config_row[0],image.config_digest)
                self.assertEqual(state.config_row[2],image.target_digest)
                self.assertEqual(state.import_rows[0][0],imported)
                self.assertFalse(state.canonical_present)

    def test_foreign_config_refs_targets_and_incomplete_rows_never_bind(self):
        for fault in ['config','foreign-ref','duplicate','tag','config-target','import-target','import-type','incomplete','canonical-target']:
            with self.subTest(fault=fault):
                image, imported, table, status = fixture(canonical=True)
                if fault == 'config': status['status']['id'] = 'sha256:'+'c'*64
                elif fault == 'foreign-ref': status['status']['repoDigests'] = ['docker.io/foreign/image@sha256:'+'a'*64]
                elif fault == 'duplicate': status['status']['repoDigests'] *= 2
                elif fault == 'tag': status['status']['repoTags'] = ['foreign/image:latest']
                elif fault == 'config-target': table = table.replace((image.config_digest+' application/vnd.oci.image.manifest.v1+json '+image.target_digest).encode(),(image.config_digest+' application/vnd.oci.image.manifest.v1+json sha256:'+'c'*64).encode())
                elif fault == 'import-target': table = table.replace((imported+' application/vnd.oci.image.index.v1+json sha256:'+'a'*64).encode(),(imported+' application/vnd.oci.image.index.v1+json sha256:'+'c'*64).encode())
                elif fault == 'import-type': table = table.replace((imported+' application/vnd.oci.image.index.v1+json').encode(),(imported+' application/vnd.docker.distribution.manifest.v2+json').encode())
                elif fault == 'incomplete': table = table.replace(b'complete (7/7)',b'complete (6/7)')
                else: table = table.replace(('kil.local/kil-v3b2@'+image.target_digest+' application/vnd.oci.image.manifest.v1+json '+image.target_digest).encode(),('kil.local/kil-v3b2@'+image.target_digest+' application/vnd.oci.image.manifest.v1+json sha256:'+'c'*64).encode())
                with self.assertRaises(ValueError): self.analyse(table,status,'kil')

    def test_older_unassociated_imports_are_never_selected(self):
        image, imported, table, status = fixture('envoy',True)
        old = 'import-2026-06-02@sha256:'+'d'*64
        table += (old+' application/vnd.oci.image.index.v1+json sha256:'+'d'*64+' complete (4/4) 1.0 MiB true\n').encode()
        state = self.analyse(table,status,'envoy')
        self.assertTrue(state.canonical_present)
        self.assertEqual([row[0] for row in state.import_rows],[imported])

    def test_actual_equal_dual_size_format_keeps_same_config_association(self):
        image, imported, table, status = fixture('envoy')
        state = self.analyse(table.replace(b'46.4 MiB true',b'46.4 MiB/46.4 MiB true'),status,'envoy')
        self.assertEqual(state.config_row[2],image.target_digest)
        self.assertEqual(state.import_rows[0][0],imported)

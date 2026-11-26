from demo import CLIPS, gesture, proof_input, rectangle
from tests import HttpCase


class TestEdition(HttpCase):
    def test_issued_clip_is_fixed(self):
        old_clip = self.clip()
        old_proof = self.proof(old_clip['clip_id'])
        first = self.issue(old_proof)
        replacement = self.clip('B')
        revised_proof = self.proof(replacement['clip_id'])
        second = self.issue(revised_proof)

        self.assertNotEqual(first['edition_id'], second['edition_id'])
        self.assertEqual(self.get('/drafts/optics')['revision_id'], revised_proof['proof_id'])
        self.assertEqual(self.get(f"/proofs/{old_proof['proof_id']}"), old_proof)
        retained = self.get(f"/editions/{first['edition_id']}")
        self.assertEqual(retained, first)
        self.assertEqual(retained['rules'][0]['clip_id'], old_clip['clip_id'])
        self.assertEqual(second['rules'][0]['clip_id'], replacement['clip_id'])
        self.assertEqual(self.get(f"/clips/{old_clip['clip_id']}"), {
            'clip_id': old_clip['clip_id'], 'language': 'zh', 'text': '光从入口进入棱镜。',
            'duration': 3, 'source': {'exhibit': '光路', 'material_id': 'optics-zh-a'},
        })
        self.assertEqual(self.issue(old_proof)['rules'][0]['clip_id'], old_clip['clip_id'])

    def test_overlapping_regions_rejected(self):
        first = self.publish()
        draft = self.get('/drafts/optics')
        bad = proof_input(1, regions=[rectangle('L', 0, 2), rectangle('R', 1, 3)])
        conflict = self.post('/proofs', bad, status=409)
        self.assertEqual((conflict['error'], conflict['position']), ('proof_conflict', 'regions[1]'))
        self.assertEqual(self.get('/drafts/optics'), draft)
        self.assertEqual(self.get('/editions/1'), first)
        self.get('/proofs/2', status=404)

    def test_clip_language_mismatch(self):
        chinese = self.clip()
        english = self.clip('E')
        valid_rules = [gesture(chinese['clip_id']),
                       gesture(english['clip_id'], rule_id='r02', language='en')]
        proof = self.proof(chinese['clip_id'], rules=valid_rules)
        first = self.issue(proof)
        invalid_rules = [gesture(english['clip_id']), valid_rules[1]]
        bad = proof_input(chinese['clip_id'], rules=invalid_rules)
        conflict = self.post('/proofs', bad, status=409)
        self.assertEqual(conflict['position'], 'rules[0].clip_id')
        self.assertIn('language', conflict['message'])
        self.assertEqual(self.get('/proofs/1'), proof)
        self.assertEqual(self.get('/drafts/optics')['revision_id'], proof['proof_id'])
        self.assertEqual(self.get('/editions/1'), first)
        self.get('/proofs/2', status=404)
        self.get('/editions/2', status=404)

    def test_unknown_issue(self):
        edition = self.publish()
        self.assertEqual(self.post('/editions', {'proof_id': 91}, status=404)['error'], 'unknown_proof')
        self.assertEqual(self.get('/editions/91', status=404)['error'], 'unknown_edition')
        self.assertEqual(self.get('/editions/1'), edition)
        self.get('/editions/2', status=404)

    def test_shared_edge(self):
        clip = self.clip()
        regions = [rectangle('L', 0, 2), rectangle('R', 2, 4)]
        edition = self.issue(self.proof(clip['clip_id'], regions=regions))
        self.assertEqual(edition['regions'], regions)
        self.assertEqual(self.get('/editions/1'), edition)

    def test_rule_pair_conflict(self):
        clip = self.clip()
        accepted = self.proof(clip['clip_id'])
        conflicting = [gesture(clip['clip_id']),
                       gesture(clip['clip_id'], rule_id='r02', endpoints=('R', 'L'))]
        bad = self.post('/proofs', proof_input(clip['clip_id'], rules=conflicting), status=409)
        self.assertEqual(bad['position'], 'rules[1].regions')
        self.assertEqual(self.get('/drafts/optics')['revision_id'], accepted['proof_id'])
        self.assertEqual(self.get('/proofs/1'), accepted)
        self.get('/proofs/2', status=404)

    def test_clip_intake(self):
        missing_text = {key: value for key, value in CLIPS['A'].items() if key != 'text'}
        invalid = (CLIPS['A'] | {'duration': 0}, CLIPS['A'] | {'duration': True},
                   missing_text, CLIPS['A'] | {'material_id': '  '})
        for sample in invalid:
            with self.subTest(sample=sample):
                self.assertEqual(self.post('/clips', sample, status=400)['error'], 'invalid_clip')
                self.assertEqual(self.get('/clips/1', status=404)['error'], 'unknown_clip')
        clip = self.clip()
        self.assertEqual(clip['clip_id'], 1)
        edition = self.issue(self.proof(clip['clip_id']))
        self.assertEqual(edition['rules'][0]['clip_id'], 1)

    def test_language_scope(self):
        chinese = self.clip()
        english = self.clip('E')
        rules = [gesture(chinese['clip_id'], endpoints=('R', 'L')),
                 gesture(english['clip_id'], rule_id='r02', language='en')]
        edition = self.issue(self.proof(chinese['clip_id'], rules=rules))
        self.assertEqual([(r['regions'], r['language'], r['clip_id']) for r in edition['rules']],
                         [(['L', 'R'], 'zh', 1), (['L', 'R'], 'en', 2)])
        session_id = self.install(edition, 'en')['session_id']
        self.down(session_id, 'A', 1, 1)
        self.down(session_id, 'B', 1, 3)
        plays = self.advance(session_id, 5)
        self.assertEqual([(r['rule_id'], r['text']) for r in plays], [('r02', 'Light enters the prism.')])

    def test_invalid_geometry_and_rule_inputs_preserve_proof(self):
        accepted = self.publish()
        cases = [
            (proof_input(1, regions=[rectangle('L', False, 2)]), 'regions[0].x0'),
            (proof_input(1, regions=[rectangle('L', 0, 0)]), 'regions[0]'),
            (proof_input(1, rules=[gesture(1, endpoints=('L', 'L'))]), 'rules[0].regions'),
            (proof_input(1, rules=[gesture(1, endpoints=('L', 'X'))]), 'rules[0].regions[1]'),
            (proof_input(1, rules=[gesture(90)]), 'rules[0].clip_id'),
            (proof_input(1, rules=[gesture(1, wait=True)]), 'rules[0].wait'),
        ]
        for request, position in cases:
            with self.subTest(position=position):
                self.assertEqual(self.post('/proofs', request, status=409)['position'], position)
        self.assertEqual(self.get('/drafts/optics')['revision_id'], 1)
        self.assertEqual(self.get('/editions/1'), accepted)
        self.get('/proofs/2', status=404)

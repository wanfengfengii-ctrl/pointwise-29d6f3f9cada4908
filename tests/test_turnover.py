from tests import HttpCase


class TestTurnover(HttpCase):
    def _listen(self, edition):
        session = self.install(edition)
        self.assertEqual((session['tick'], session['event_seq']), (0, 0))
        session_id = session['session_id']
        self.down(session_id, 'A1', 1, 1)
        self.down(session_id, 'B1', 1, 3)
        self.assertEqual(self.advance(session_id, 4), [])
        plays = self.advance(session_id, 5)
        self.assertEqual([(p['tick'], p['contacts']) for p in plays], [(5, ['A1', 'B1'])])
        self.up(session_id, 'A1', 5)
        self.up(session_id, 'B1', 5)
        return session_id, plays

    def _two_sessions(self):
        first_edition = self.publish()
        first_id, first_plays = self._listen(first_edition)
        first_receipt = self.close(first_id)
        next_edition = self.publish('B')
        next_id, next_plays = self._listen(next_edition)
        next_receipt = self.close(next_id)
        return (first_edition, first_id, first_plays, first_receipt), (next_edition, next_id, next_plays, next_receipt)

    def test_review_survives_next_install(self):
        previous, current = self._two_sessions()
        first_edition, first_id, first_plays, first_receipt = previous
        next_edition, next_id, next_plays, next_receipt = current
        self.assertEqual(self.get('/station')['session']['session_id'], next_id)
        self.assertEqual(first_receipt, {'session_id': first_id, 'edition_id': first_edition['edition_id'],
                                        'language': 'zh', 'last_ordinal': 1, 'closed_tick': 5})
        self.assertEqual(self.review(first_id), {'receipt': first_receipt, 'plays': first_plays})
        self.assertEqual(self.review(next_id), {'receipt': next_receipt, 'plays': next_plays})
        self.assertEqual([(p['edition_id'], p['clip_id'], p['source']['material_id'])
                          for p in first_plays + next_plays],
                         [(first_edition['edition_id'], 1, 'optics-zh-a'),
                          (next_edition['edition_id'], 2, 'optics-zh-b')])

    def test_close_busy(self):
        session_id, plays = self._listen(self.publish())
        self.down(session_id, 'outside', 6, 10)
        before = self.get(f'/sessions/{session_id}')
        self.assertEqual(self.post(f'/sessions/{session_id}/close', {}, status=409)['error'], 'close_conflict')
        self.assertEqual(self.get(f'/sessions/{session_id}/review', status=409)['error'], 'review_pending')
        self.assertEqual(self.get(f'/sessions/{session_id}'), before)
        self.assertEqual(self.up(session_id, 'outside', 7)['active'], [])
        receipt = self.close(session_id)
        self.assertEqual((receipt['last_ordinal'], receipt['closed_tick']), (1, 7))
        self.assertEqual(self.review(session_id)['plays'], plays)

    def test_review_states(self):
        self.assertEqual(self.get('/sessions/70/review', status=404)['error'], 'unknown_session')
        session_id = self.install(self.publish())['session_id']
        self.assertEqual(self.get(f'/sessions/{session_id}/review', status=409)['error'], 'review_pending')
        receipt = self.close(session_id)
        self.assertEqual(receipt, {'session_id': session_id, 'edition_id': 1, 'language': 'zh',
                                   'last_ordinal': 0, 'closed_tick': 0})
        self.assertEqual(self.close(session_id), receipt)
        self.assertEqual(self.review(session_id), {'receipt': receipt, 'plays': []})

    def test_empty_install(self):
        old_session, plays = self._listen(self.publish())
        next_edition = self.publish('B')
        self.assertEqual(self.get(f'/sessions/{old_session}/review', status=409)['error'], 'review_pending')
        new_session = self.install(next_edition)
        self.assertEqual(new_session, {'session_id': 2, 'edition_id': next_edition['edition_id'],
                                      'language': 'zh', 'tick': 0, 'event_seq': 0, 'closed': False})
        review = self.review(old_session)
        self.assertEqual(review, {'receipt': {'session_id': old_session, 'edition_id': 1, 'language': 'zh',
                                              'last_ordinal': 1, 'closed_tick': 5}, 'plays': plays})
        self.assertEqual(self.close(old_session), review['receipt'])

    def test_restart(self):
        previous, current = self._two_sessions()
        changed = self.proof(2, regions=[
            {'region_id': 'L', 'name': '入口修订', 'x0': 0, 'x1': 2, 'y0': 0, 'y1': 2},
            {'region_id': 'R', 'name': '出口修订', 'x0': 2, 'x1': 4, 'y0': 0, 'y1': 2},
        ])
        latest = self.get('/drafts/optics')
        clips = [self.get('/clips/1'), self.get('/clips/2')]
        self.reopen()
        self.assertEqual(self.get('/drafts/optics'), latest)
        self.assertEqual(self.get(f"/proofs/{changed['proof_id']}"), changed)
        self.assertEqual(latest['regions'][0]['name'], '入口修订')
        for edition, session_id, plays, receipt in (previous, current):
            with self.subTest(session_id=session_id):
                self.assertEqual(self.get(f"/editions/{edition['edition_id']}"), edition)
                self.assertEqual(self.review(session_id), {'receipt': receipt, 'plays': plays})
                self.assertEqual(self.close(session_id), receipt)
        self.assertEqual(self.get('/station')['session']['session_id'], current[1])
        self.assertEqual([self.get('/clips/1'), self.get('/clips/2')], clips)
        self.get('/clips/3', status=404)
        self.get('/editions/3', status=404)
        self.get('/sessions/3', status=404)

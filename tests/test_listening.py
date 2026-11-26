from contextlib import closing
import sqlite3

from demo import contact_input, gesture, install_input, rectangle
from tests import HttpCase


class TestListening(HttpCase):
    def _hold_pair(self, session_id, tick=1):
        first = self.down(session_id, 'A1', tick, 1)
        second = self.down(session_id, 'B1', tick, 3)
        self.assertEqual((first['event_seq'], second['event_seq']), (1, 2))
        self.assertEqual([contact['contact_id'] for contact in second['active']], ['A1', 'B1'])
        return second

    def test_two_contacts_fire_on_deadline(self):
        edition = self.publish()
        session_id = self.install(edition)['session_id']
        self._hold_pair(session_id)
        self.assertEqual(self.advance(session_id, 4), [])
        self.assertEqual(self.advance(session_id, 5), [{
            'play_id': 1, 'session_id': session_id, 'edition_id': edition['edition_id'],
            'rule_id': 'r01', 'contacts': ['A1', 'B1'], 'tick': 5, 'clip_id': 1, 'ordinal': 1,
            'text': '光从入口进入棱镜。', 'duration': 3,
            'source': {'exhibit': '光路', 'material_id': 'optics-zh-a'},
        }])
        self.assertEqual(self.advance(session_id, 6), [])

    def test_released_contact_breaks_wait(self):
        session_id = self.install(self.publish())['session_id']
        self._hold_pair(session_id)
        self.up(session_id, 'B1', 4)
        self.down(session_id, 'B2', 4, 3)
        self.assertEqual(self.advance(session_id, 5), [])
        plays = self.advance(session_id, 8)
        self.assertEqual([(p['tick'], p['contacts']) for p in plays], [(8, ['A1', 'B2'])])

    def test_release_of_first_ordered_contact_breaks_wait(self):
        session_id = self.install(self.publish())['session_id']
        self._hold_pair(session_id)
        self.up(session_id, 'A1', 4)
        self.down(session_id, 'A2', 4, 1)
        self.assertEqual(self.advance(session_id, 5), [])
        plays = self.advance(session_id, 8)
        self.assertEqual([(p['tick'], p['contacts']) for p in plays], [(8, ['A2', 'B1'])])

    def test_busy_station_rejects_install(self):
        original = self.publish()
        replacement = self.publish('B')
        session_id = self.install(original)['session_id']
        self._hold_pair(session_id)
        self.assertEqual(self.advance(session_id, 3), [])
        before = self.get('/station')
        error = self.post('/station/install', install_input(replacement['edition_id']), status=409)
        self.assertEqual(error['error'], 'install_conflict')
        self.assertEqual(self.get('/station'), before)
        self.assertEqual(self.advance(session_id, 4), [])
        plays = self.advance(session_id, 5)
        self.assertEqual([(p['edition_id'], p['clip_id'], p['tick']) for p in plays], [(1, 1, 5)])

    def test_clock_reversal_rejected(self):
        session_id = self.install(self.publish())['session_id']
        self._hold_pair(session_id)
        original = self.advance(session_id, 5)
        self.assertEqual([(p['tick'], p['ordinal']) for p in original], [(5, 1)])
        error = self.post(f'/sessions/{session_id}/advance', {'tick': 4}, status=409)
        self.assertEqual(error['error'], 'clock_conflict')
        self.assertEqual(self.get(f'/sessions/{session_id}')['tick'], 5)
        late = contact_input('down', 'late', 4, 1, 1)
        self.assertEqual(self.post(f'/sessions/{session_id}/contacts', late, status=409)['error'],
                         'clock_conflict')
        self.up(session_id, 'A1', 5)
        self.up(session_id, 'B1', 5)
        self.close(session_id)
        self.assertEqual(self.review(session_id)['plays'], original)

    def test_contact_geometry(self):
        session_id = self.install(self.publish())['session_id']
        self.down(session_id, 'A', 1, 0, 0)
        self.down(session_id, 'B', 1, 1, 1)
        outside = self.down(session_id, 'Xedge', 1, 4, 1)
        self.assertEqual([c['contact_id'] for c in outside['active']], ['A', 'B', 'Xedge'])
        self.down(session_id, 'Yedge', 1, 2, 2)
        self.assertEqual(self.advance(session_id, 5), [])
        self.down(session_id, 'Shared', 6, 2, 0)
        self.assertEqual(self.advance(session_id, 9), [])
        plays = self.advance(session_id, 10)
        self.assertEqual([p['contacts'] for p in plays], [['A', 'Shared'], ['B', 'Shared']])

    def _two_rules(self, waits=(4, 4)):
        clip = self.clip()
        regions = [rectangle('L', 0, 2), rectangle('R', 2, 4),
                   rectangle('C', 4, 6), rectangle('D', 6, 8)]
        rules = [gesture(clip['clip_id'], rule_id='r01', wait=waits[0]),
                 gesture(clip['clip_id'], rule_id='r02', endpoints=('C', 'D'), wait=waits[1])]
        edition = self.issue(self.proof(clip['clip_id'], regions=regions, rules=rules))
        return self.install(edition)['session_id']

    def test_due_order(self):
        session_id = self._two_rules()
        for contact_id, x in [('C', 5), ('D', 7), ('B', 1), ('Z', 3), ('A', 1)]:
            self.down(session_id, contact_id, 1, x)
        plays = self.advance(session_id, 5)
        self.assertEqual([(p['rule_id'], p['contacts'], p['ordinal']) for p in plays], [
            ('r01', ['A', 'Z'], 1), ('r01', ['B', 'Z'], 2), ('r02', ['C', 'D'], 3),
        ])
        for contact_id in ('A', 'B', 'C', 'D', 'Z'):
            self.up(session_id, contact_id, 5)
        self.close(session_id)
        self.assertEqual(self.review(session_id)['plays'], plays)

    def test_deadline_precedes_rule_order(self):
        session_id = self._two_rules(waits=(4, 2))
        for contact_id, x in [('A', 1), ('B', 3), ('C', 5), ('D', 7)]:
            self.down(session_id, contact_id, 1, x)
        plays = self.advance(session_id, 6)
        self.assertEqual([(p['rule_id'], p['tick']) for p in plays], [('r02', 6), ('r01', 6)])

    def test_advance_target(self):
        session_id = self.install(self.publish())['session_id']
        self._hold_pair(session_id)
        self.assertEqual([p['tick'] for p in self.advance(session_id, 6)], [6])
        self.assertEqual(self.advance(session_id, 6), [])

        zero = self.issue(self.proof(1, rules=[gesture(1, wait=0)]))
        self.up(session_id, 'A1', 6)
        self.up(session_id, 'B1', 6)
        next_session = self.install(zero)['session_id']
        self._hold_pair(next_session, 0)
        self.assertEqual([p['tick'] for p in self.advance(next_session, 0)], [0])
        self.assertEqual(self.advance(next_session, 0), [])

    def test_contact_errors(self):
        session_id = self.install(self.publish())['session_id']
        held = self._hold_pair(session_id)
        before = self.get(f'/sessions/{session_id}')
        bad_events = [contact_input('down', 'A1', 4, 3, 1), contact_input('up', 'unknown', 4),
                      contact_input('down', 'X', 4, True, 1), contact_input('down', 'Y', 4, 2.5, 1)]
        for event in bad_events:
            error = self.post(f'/sessions/{session_id}/contacts', event, status=409)
            self.assertEqual(error['error'], 'contact_conflict')
            self.assertEqual(self.get(f'/sessions/{session_id}'), before)
        still_held = self.down(session_id, 'outside', 2, 8)
        self.assertEqual(still_held['active'][:2], held['active'])
        self.assertEqual(still_held['event_seq'], 3)
        self.assertEqual(self.advance(session_id, 4), [])
        self.assertEqual([p['contacts'] for p in self.advance(session_id, 5)], [['A1', 'B1']])
        self.up(session_id, 'A1', 6)
        reused = contact_input('down', 'A1', 6, 1, 1)
        self.assertEqual(self.post(f'/sessions/{session_id}/contacts', reused, status=409)['error'],
                         'contact_conflict')

    def test_install_inputs(self):
        first = self.publish()
        english = self.clip('E')
        english_only = self.issue(self.proof(english['clip_id'], rules=[gesture(english['clip_id'], language='en')]))
        self.install(first)
        before = self.get('/station')
        self.assertEqual(self.post('/station/install', install_input(82), status=404)['error'], 'unknown_edition')
        self.assertEqual(self.get('/station'), before)
        wrong = install_input(english_only['edition_id'])
        self.assertEqual(self.post('/station/install', wrong, status=409)['error'], 'install_conflict')
        self.assertEqual(self.get('/station'), before)
        self.assertEqual(self.get('/sessions/1/review', status=409)['error'], 'review_pending')
        installed = self.install(english_only, 'en')
        self.assertEqual((installed['session_id'], installed['tick'], installed['language']), (2, 0, 'en'))

    def test_press_reversal(self):
        session_id = self.install(self.publish())['session_id']
        self._hold_pair(session_id)
        original = self.advance(session_id, 5)
        self.assertEqual([p['contacts'] for p in original], [['A1', 'B1']])
        before = self.get(f'/sessions/{session_id}')
        for event in [contact_input('up', 'B1', 4), contact_input('down', 'B2', 4, 3, 1)]:
            self.assertEqual(self.post(f'/sessions/{session_id}/contacts', event, status=409)['error'],
                             'clock_conflict')
            self.assertEqual(self.get(f'/sessions/{session_id}'), before)
        release = self.up(session_id, 'A1', 5)
        self.assertEqual(release['event_seq'], 3)
        self.assertEqual([c['contact_id'] for c in release['active']], ['B1'])
        self.up(session_id, 'B1', 5)
        self.close(session_id)
        self.assertEqual(self.review(session_id)['plays'], original)

    def test_closed_advance(self):
        session_id = self.install(self.publish())['session_id']
        self._hold_pair(session_id)
        original = self.advance(session_id, 5)
        self.assertEqual(len(original), 1)
        self.up(session_id, 'A1', 5)
        self.up(session_id, 'B1', 5)
        receipt = self.close(session_id)
        self.assertEqual(self.post(f'/sessions/{session_id}/advance', {'tick': 6}, status=409)['error'],
                         'session_conflict')
        self.assertEqual(self.close(session_id), receipt)
        self.assertEqual(self.review(session_id), {'receipt': receipt, 'plays': original})

    def test_advance_rolls_back_when_second_play_write_fails(self):
        session_id = self._two_rules()
        for contact_id, x in [('A', 1), ('B', 3), ('C', 5), ('D', 7)]:
            self.down(session_id, contact_id, 1, x)
        before = self.get(f'/sessions/{session_id}')
        with closing(sqlite3.connect(self.database, isolation_level=None)) as db:
            db.execute('''CREATE TRIGGER reject_second_play BEFORE INSERT ON plays
                          WHEN NEW.rule_id = 'r02'
                          BEGIN SELECT RAISE(ABORT, 'test write failure'); END''')
            error = self.post(f'/sessions/{session_id}/advance', {'tick': 5}, status=500)
            self.assertEqual(error['error'], 'storage_error')
            self.assertEqual(self.get(f'/sessions/{session_id}'), before)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM plays').fetchone()[0], 0)
            db.execute('DROP TRIGGER reject_second_play')

        plays = self.advance(session_id, 5)
        self.assertEqual([(p['rule_id'], p['tick'], p['ordinal']) for p in plays],
                         [('r01', 5, 1), ('r02', 5, 2)])
        self.assertEqual(self.advance(session_id, 5), [])

    def test_large_integer_deadline_remains_exact(self):
        session_id = self.install(self.publish())['session_id']
        start = 2**70
        self._hold_pair(session_id, start)
        self.assertEqual(self.advance(session_id, start + 3), [])
        self.assertEqual([p['tick'] for p in self.advance(session_id, start + 4)], [start + 4])

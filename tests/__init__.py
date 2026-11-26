from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from demo import CLIPS, contact_input, install_input, proof_input, running_station


class HttpCase(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.database = Path(directory) / 'test.sqlite3'
        self.service = self.enterContext(ExitStack())
        self.reopen()

    def reopen(self):
        self.service.close()
        self.client = self.service.enter_context(running_station(self.database))

    def get(self, path, *, status=200):
        return self.client.expect('GET', path, status=status)

    def post(self, path, body, *, status=200):
        return self.client.expect('POST', path, body, status=status)

    def clip(self, sample='A'):
        return self.post('/clips', CLIPS[sample], status=201)

    def proof(self, clip_id, **options):
        return self.post('/proofs', proof_input(clip_id, **options), status=201)

    def issue(self, proof):
        return self.post('/editions', {'proof_id': proof['proof_id']}, status=201)

    def publish(self, sample='A', **options):
        clip = self.clip(sample)
        return self.issue(self.proof(clip['clip_id'], **options))

    def install(self, edition, language='zh'):
        return self.post('/station/install', install_input(edition['edition_id'], language),
                         status=201)['session']

    def down(self, session_id, contact_id, tick, x, y=1):
        return self.post(f'/sessions/{session_id}/contacts', contact_input('down', contact_id, tick, x, y))

    def up(self, session_id, contact_id, tick):
        return self.post(f'/sessions/{session_id}/contacts', contact_input('up', contact_id, tick))

    def advance(self, session_id, tick):
        return self.post(f'/sessions/{session_id}/advance', {'tick': tick})['plays']

    def close(self, session_id):
        return self.post(f'/sessions/{session_id}/close', {})

    def review(self, session_id):
        return self.get(f'/sessions/{session_id}/review')

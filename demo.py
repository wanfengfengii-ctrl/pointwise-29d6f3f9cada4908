from contextlib import contextmanager
from http.client import HTTPConnection
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from station.http import create_server


CLIPS = {
    'A': {'exhibit': '光路', 'language': 'zh', 'text': '光从入口进入棱镜。',
          'material_id': 'optics-zh-a', 'duration': 3},
    'B': {'exhibit': '光路', 'language': 'zh', 'text': '在出口辨认分开的光。',
          'material_id': 'optics-zh-b', 'duration': 5},
    'E': {'exhibit': '光路', 'language': 'en', 'text': 'Light enters the prism.',
          'material_id': 'optics-en-a', 'duration': 4},
}


def rectangle(region_id, x0, x1, y0=0, y1=2):
    return {'region_id': region_id, 'name': region_id, 'x0': x0, 'x1': x1, 'y0': y0, 'y1': y1}


def gesture(clip_id, *, rule_id='r01', language='zh', endpoints=('L', 'R'), wait=4):
    return {'rule_id': rule_id, 'name': '光路讲解', 'regions': list(endpoints),
            'language': language, 'clip_id': clip_id, 'wait': wait}


def proof_input(clip_id, *, draft_id='optics', regions=None, rules=None):
    return {
        'draft_id': draft_id,
        'regions': [rectangle('L', 0, 2), rectangle('R', 2, 4)] if regions is None else regions,
        'rules': [gesture(clip_id)] if rules is None else rules,
    }


def install_input(edition_id, language='zh'):
    return {'station_id': 'main', 'edition_id': edition_id, 'language': language}


def contact_input(action, contact_id, tick, x=None, y=None):
    event = {'action': action, 'contact_id': contact_id, 'tick': tick}
    if action == 'down':
        event.update(x=x, y=y)
    return event


class Client:
    def __init__(self, port):
        self.port = port

    def request(self, method, path, body=None):
        connection = HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            if body is None:
                connection.request(method, path)
            else:
                encoded = json.dumps(body, ensure_ascii=False).encode('utf-8')
                connection.request(method, path, encoded, {'Content-Type': 'application/json'})
            with connection.getresponse() as response:
                return response.status, json.loads(response.read())
        finally:
            connection.close()

    def expect(self, method, path, body=None, *, status=200):
        actual_status, result = self.request(method, path, body)
        if actual_status != status:
            raise AssertionError(f'{method} {path}: expected {status}, got {actual_status}: {result!r}')
        return result


@contextmanager
def running_station(path):
    with create_server(path) as server:
        worker = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02})
        worker.start()
        try:
            yield Client(server.server_port)
        finally:
            server.shutdown()
            worker.join()


def _play_facts(events):
    return [[event['edition_id'], event['rule_id'], event['contacts'], event['tick'],
             event['clip_id'], event['source']['material_id']] for event in events]


def run_demo(client):
    def issue(clip_id):
        proof = client.expect('POST', '/proofs', proof_input(clip_id), status=201)
        return client.expect('POST', '/editions', {'proof_id': proof['proof_id']}, status=201)

    def install(edition_id):
        return client.expect('POST', '/station/install', install_input(edition_id), status=201)['session']

    inquiries = [contact_input('down', 'A1', 1, 1, 1), contact_input('down', 'B1', 1, 3, 1)]

    def contacts(session_id, events):
        for event in events:
            client.expect('POST', f'/sessions/{session_id}/contacts', event)

    def advance(session_id, tick):
        return client.expect('POST', f'/sessions/{session_id}/advance', {'tick': tick})['plays']

    def finish(session_id, tick):
        contacts(session_id, [contact_input('up', 'A1', tick), contact_input('up', 'B1', tick)])
        return client.expect('POST', f'/sessions/{session_id}/close', {})

    first_clip = client.expect('POST', '/clips', CLIPS['A'], status=201)
    first_edition = issue(first_clip['clip_id'])
    next_clip = client.expect('POST', '/clips', CLIPS['B'], status=201)
    next_edition = issue(next_clip['clip_id'])
    retained = client.expect('GET', f"/editions/{first_edition['edition_id']}")
    if retained != first_edition:
        raise AssertionError('editing the draft changed the first issued bundle')

    first_id = install(first_edition['edition_id'])['session_id']
    contacts(first_id, inquiries)
    before = advance(first_id, 4)
    at_deadline = advance(first_id, 5)
    after = advance(first_id, 6)
    receipt = finish(first_id, 6)

    next_id = install(next_edition['edition_id'])['session_id']
    contacts(next_id, inquiries)
    next_plays = advance(next_id, 5)
    finish(next_id, 5)
    review = client.expect('GET', f'/sessions/{first_id}/review')
    next_review = client.expect('GET', f'/sessions/{next_id}/review')

    expected_first = [1, 'r01', ['A1', 'B1'], 5, 1, 'optics-zh-a']
    expected_next = [2, 'r01', ['A1', 'B1'], 5, 2, 'optics-zh-b']
    expected = [[], [expected_first], [], [expected_next]]
    actual = [_play_facts(events) for events in (before, at_deadline, after, next_plays)]
    downstream_expected = {
        'receipt': {'session_id': 1, 'edition_id': 1, 'language': 'zh',
                    'last_ordinal': 1, 'closed_tick': 6},
        'first': [expected_first],
        'next': [expected_next],
    }
    downstream_actual = {'receipt': review['receipt'], 'first': _play_facts(review['plays']),
                         'next': _play_facts(next_review['plays'])}
    if actual != expected or downstream_actual != downstream_expected:
        raise AssertionError((actual, downstream_actual))
    if review != {'receipt': receipt, 'plays': at_deadline} or next_review['plays'] != next_plays:
        raise AssertionError('review differs from the original device response')
    if [at_deadline[0]['text'], next_plays[0]['text']] != [CLIPS['A']['text'], CLIPS['B']['text']]:
        raise AssertionError('device responses did not carry the issued clip text')

    evidence = {
        'case_id': 'v7',
        'input': {'clips': [CLIPS['A'], CLIPS['B']], 'drafts': [proof_input(1), proof_input(2)],
                  'contacts_per_session': inquiries, 'advance_ticks': [[4, 5, 6], [5]]},
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': ['layout/proof.py', 'edition/issue.py', 'station/install.py',
                       'station/matching.py', 'station/waits.py', 'station/ticks.py',
                       'performance/records.py', 'performance/review.py'],
        'oracle': '手工核对两个半开区间的命中和 1 + 4 = 5。按两次签发顺序分别核对原实播出处与原场回执。',
    }
    print('POINTWISE_SCENARIO ' + json.dumps(evidence, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    with TemporaryDirectory() as directory:
        with running_station(Path(directory) / 'station.sqlite3') as station:
            run_demo(station)

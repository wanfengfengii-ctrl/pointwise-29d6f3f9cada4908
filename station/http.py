import argparse
from contextlib import closing
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import sqlite3
from urllib.parse import unquote, urlsplit

from audio.content import InvalidClip
from audio.intake import register_clip
from audio.retrieve import UnknownClip, retrieve_clip
from edition.carry import CarryConflict, CarryRepository
from edition.catalog import EditionCatalog, IssuedEdition, UnknownEdition
from edition.issue import issue_layout, issue_successor
from edition.verify import InvalidEditionBundle
from layout.drafts import DraftRepository
from layout.proof import ProofConflict, UnknownProof, create_proof, get_proof
from performance.close import CloseConflict, close_session
from performance.review import ReviewPending, review_session
from station.contacts import ContactConflict, press
from station.database import initialize_database, open_database, request_transaction
from station.install import InstallConflict, STATION_ID, install_layout
from station.session import ClockConflict, SessionConflict, SessionRepository, UnknownSession
from station.switching import SwitchConflict, switch_edition
from station.ticks import advance


class RequestError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


ERROR_RESPONSES = {
    InvalidClip: (400, 'invalid_clip'),
    UnknownClip: (404, 'unknown_clip'),
    UnknownProof: (404, 'unknown_proof'),
    UnknownEdition: (404, 'unknown_edition'),
    UnknownSession: (404, 'unknown_session'),
    ProofConflict: (409, 'proof_conflict'),
    InvalidEditionBundle: (409, 'invalid_edition'),
    CarryConflict: (409, 'carry_conflict'),
    SwitchConflict: (409, 'switch_conflict'),
    InstallConflict: (409, 'install_conflict'),
    ContactConflict: (409, 'contact_conflict'),
    ClockConflict: (409, 'clock_conflict'),
    SessionConflict: (409, 'session_conflict'),
    CloseConflict: (409, 'close_conflict'),
    ReviewPending: (409, 'review_pending'),
}
BUSINESS_ERRORS = tuple(ERROR_RESPONSES)
MAX_BODY_BYTES = 1024 * 1024


def _bad_request(message: str) -> RequestError:
    return RequestError(400, 'bad_request', message)


def _unknown_route() -> RequestError:
    return RequestError(404, 'unknown_route', 'unknown route')


def _positive_id(value: object) -> int:
    if type(value) is not int or not 0 < value < 2**63:
        raise _bad_request('expected a positive numeric ID')
    return value


def _path_id(segment: str) -> int:
    if re.fullmatch(r'[0-9]{1,19}', segment) is None:
        raise _bad_request('expected a positive numeric path ID')
    return _positive_id(int(segment))


def _fields(body: object, required=(), optional=()) -> None:
    if not isinstance(body, dict):
        raise _bad_request('expected a JSON object')
    missing = set(required) - body.keys()
    if missing:
        raise _bad_request('missing fields: ' + ', '.join(sorted(missing)))
    extra = body.keys() - set(required) - set(optional)
    if extra:
        raise _bad_request('unknown fields: ' + ', '.join(sorted(extra)))


def _edition_response(edition: IssuedEdition, carry=None) -> dict:
    response = {'edition_id': edition.edition_id, **asdict(edition.bundle)}
    if carry is not None:
        response.update(
            parent_edition_id=carry.parent_edition_id,
            region_carry=carry.region_carry,
            rule_carry=carry.rule_carry,
        )
    return response


def _get(db: sqlite3.Connection, parts: list[str]) -> dict:
    if parts == ['station']:
        current = SessionRepository(db).current()
        return {'station_id': STATION_ID, 'session': None if current is None else asdict(current)}
    if len(parts) == 2:
        resource, identifier = parts
        if resource == 'clips':
            return asdict(retrieve_clip(db, _path_id(identifier)))
        if resource == 'drafts':
            try:
                draft_id = unquote(identifier, encoding='utf-8', errors='strict')
            except UnicodeError as error:
                raise _bad_request('draft ID must be UTF-8') from error
            draft = DraftRepository(db).get(draft_id)
            if draft is None:
                raise RequestError(404, 'unknown_draft', 'unknown draft')
            return asdict(draft)
        if resource == 'proofs':
            return asdict(get_proof(db, _path_id(identifier)))
        if resource == 'editions':
            edition = EditionCatalog(db).get(_path_id(identifier))
            carry = CarryRepository(db).get(edition.edition_id)
            return _edition_response(edition, carry)
        if resource == 'sessions':
            return asdict(SessionRepository(db).get(_path_id(identifier)))
    if len(parts) == 3 and parts[0] == 'sessions' and parts[2] == 'review':
        return asdict(review_session(db, _path_id(parts[1])))
    raise _unknown_route()


def _post(db: sqlite3.Connection, parts: list[str], body: object) -> tuple[int, dict]:
    if parts == ['clips']:
        _fields(body, optional=('exhibit', 'language', 'text', 'material_id', 'duration'))
        return 201, asdict(register_clip(db, body))
    if parts == ['proofs']:
        _fields(body, ('draft_id', 'regions', 'rules'))
        return 201, asdict(create_proof(db, **body))
    if parts == ['editions']:
        _fields(body, ('proof_id',),
                ('parent_edition_id', 'region_carry', 'rule_carry'))
        proof_id = _positive_id(body['proof_id'])
        carry_fields = ('parent_edition_id', 'region_carry', 'rule_carry')
        present = [field for field in carry_fields if field in body]
        if present and len(present) != len(carry_fields):
            raise _bad_request(
                'successor issuance requires parent_edition_id, region_carry '
                'and rule_carry together'
            )
        if not present:
            return 201, _edition_response(issue_layout(db, proof_id))
        parent_edition_id = _positive_id(body['parent_edition_id'])
        issued, carry = issue_successor(
            db, proof_id, parent_edition_id,
            body['region_carry'], body['rule_carry'],
        )
        return 201, _edition_response(issued, carry)
    if parts == ['station', 'install']:
        _fields(body, ('station_id', 'edition_id', 'language'))
        installed = install_layout(db, body['station_id'], _positive_id(body['edition_id']),
                                   body['language'])
        return 201, asdict(installed)
    if len(parts) == 3 and parts[0] == 'sessions':
        session_id = _path_id(parts[1])
        operation = parts[2]
        if operation == 'contacts':
            _fields(body, ('action', 'contact_id', 'tick'), ('x', 'y'))
            if body['action'] == 'up' and {'x', 'y'}.intersection(body):
                raise ContactConflict('release must omit coordinates')
            return 200, asdict(press(db, session_id, **body))
        if operation == 'advance':
            _fields(body, ('tick',))
            return 200, asdict(advance(db, session_id, body['tick']))
        if operation == 'switch-edition':
            _fields(body, ('edition_id', 'tick'))
            switched = switch_edition(
                db, session_id, _positive_id(body['edition_id']), body['tick']
            )
            return 200, asdict(switched)
        if operation == 'close':
            _fields(body)
            return 200, asdict(close_session(db, session_id))
    raise _unknown_route()


def handle_request(
    db: sqlite3.Connection, method: str, target: str, body: object = None
) -> tuple[int, dict]:
    try:
        try:
            url = urlsplit(target)
        except ValueError as error:
            raise _bad_request('invalid request target') from error
        if url.scheme or url.netloc or url.query or url.fragment or not url.path.startswith('/'):
            raise _bad_request('expected a local path without query parameters')
        parts = url.path[1:].split('/')
        if method not in ('GET', 'POST'):
            raise RequestError(405, 'method_not_allowed', 'use GET or POST')
        with request_transaction(db, write=method == 'POST'):
            if method == 'GET':
                return 200, _get(db, parts)
            return _post(db, parts, body)
    except RequestError as error:
        return error.status, {'error': error.code, 'message': str(error)}
    except BUSINESS_ERRORS as error:
        status, code = ERROR_RESPONSES[type(error)]
        result = {'error': code, 'message': str(error)}
        if isinstance(error, ProofConflict):
            result['position'] = error.position
        return status, result
    except sqlite3.Error:
        return 500, {'error': 'storage_error', 'message': 'database request failed'}


def _invalid_constant(value: str):
    raise ValueError(f'invalid JSON constant {value}')


def create_server(database, port: int = 0) -> HTTPServer:
    with closing(open_database(database)) as db:
        initialize_database(db)

    class Handler(BaseHTTPRequestHandler):
        def _read_json(self) -> object:
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError as error:
                raise _bad_request('invalid Content-Length') from error
            if self.headers.get('Transfer-Encoding') or not 0 < length <= MAX_BODY_BYTES:
                raise _bad_request('expected a length-delimited JSON body of at most 1 MiB')
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('incomplete body')
                body = json.loads(raw.decode('utf-8'), parse_constant=_invalid_constant)
                json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
                return body
            except (ValueError, UnicodeError, RecursionError) as error:
                raise _bad_request('invalid UTF-8 JSON body') from error

        def _reply(self, method: str) -> None:
            try:
                body = self._read_json() if method == 'POST' else None
                with closing(open_database(database)) as db:
                    status, result = handle_request(db, method, self.path, body)
            except RequestError as error:
                status, result = error.status, {'error': error.code, 'message': str(error)}
            except sqlite3.Error:
                status, result = 500, {'error': 'storage_error', 'message': 'database unavailable'}
            response = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def do_GET(self) -> None:
            self._reply('GET')

        def do_POST(self) -> None:
            self._reply('POST')

        def log_request(self, code='-', size='-') -> None:
            return

    return HTTPServer(('127.0.0.1', port), Handler)


def serve(database, port: int = 8080) -> None:
    with create_server(database, port) as server:
        print(f'Listening on http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the touch map narration station')
    parser.add_argument('--db', required=True)
    parser.add_argument('--port', type=int, default=8080)
    options = parser.parse_args()
    serve(options.db, options.port)

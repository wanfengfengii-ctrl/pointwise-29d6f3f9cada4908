from dataclasses import dataclass, replace
import sqlite3


class UnknownSession(LookupError):
    pass


class SessionConflict(ValueError):
    pass


class ClockConflict(ValueError):
    pass


@dataclass(frozen=True)
class LiveSession:
    session_id: int
    edition_id: int
    language: str
    tick: int = 0
    event_seq: int = 0
    closed: bool = False


def initialize_session_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id INTEGER PRIMARY KEY,
            edition_id INTEGER NOT NULL REFERENCES editions (edition_id),
            language TEXT NOT NULL,
            tick TEXT NOT NULL DEFAULT '0',
            event_seq INTEGER NOT NULL DEFAULT 0,
            closed INTEGER NOT NULL DEFAULT 0 CHECK (closed IN (0, 1))
        )
    ''')
    db.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS one_open_session
        ON sessions (closed) WHERE closed = 0
    ''')


class SessionRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def _decode(row: sqlite3.Row) -> LiveSession:
        return LiveSession(
            row['session_id'], row['edition_id'], row['language'],
            int(row['tick']), row['event_seq'], bool(row['closed']),
        )

    def current(self) -> LiveSession | None:
        row = self.db.execute('SELECT * FROM sessions ORDER BY session_id DESC LIMIT 1').fetchone()
        return None if row is None else self._decode(row)

    def get(self, session_id: int) -> LiveSession:
        row = self.db.execute(
            'SELECT * FROM sessions WHERE session_id = ?', (session_id,)
        ).fetchone()
        if row is None:
            raise UnknownSession(f'unknown session {session_id}')
        return self._decode(row)

    def get_open(self, session_id: int) -> LiveSession:
        session = self.get(session_id)
        if session.closed:
            raise SessionConflict('session is closed')
        return session

    def open(self, edition_id: int, language: str) -> LiveSession:
        cursor = self.db.execute(
            'INSERT INTO sessions (edition_id, language) VALUES (?, ?)', (edition_id, language)
        )
        return LiveSession(cursor.lastrowid, edition_id, language)

    def update_clock(self, session: LiveSession, tick: int, *, contact_event=False) -> LiveSession:
        if type(tick) is not int or tick < 0:
            raise ClockConflict('tick must be a nonnegative integer')
        if tick < session.tick:
            raise ClockConflict(f'tick {tick} precedes current tick {session.tick}')
        event_seq = session.event_seq + int(contact_event)
        self.db.execute(
            'UPDATE sessions SET tick = ?, event_seq = ? WHERE session_id = ?',
            (str(tick), event_seq, session.session_id),
        )
        return replace(session, tick=tick, event_seq=event_seq)

    def mark_closed(self, session_id: int) -> None:
        self.db.execute('UPDATE sessions SET closed = 1 WHERE session_id = ?', (session_id,))

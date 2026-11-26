from dataclasses import dataclass
import sqlite3

from performance.records import PlayRepository
from station.contacts import ContactRepository
from station.session import SessionRepository


class CloseConflict(ValueError):
    pass


@dataclass(frozen=True)
class CloseReceipt:
    session_id: int
    edition_id: int
    language: str
    last_ordinal: int
    closed_tick: int


def initialize_close_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS close_receipts (
            session_id INTEGER PRIMARY KEY REFERENCES sessions (session_id),
            edition_id INTEGER NOT NULL REFERENCES editions (edition_id),
            language TEXT NOT NULL,
            last_ordinal INTEGER NOT NULL,
            closed_tick TEXT NOT NULL
        )
    ''')


def get_close_receipt(db: sqlite3.Connection, session_id: int) -> CloseReceipt | None:
    row = db.execute(
        'SELECT * FROM close_receipts WHERE session_id = ?', (session_id,)
    ).fetchone()
    if row is None:
        return None
    return CloseReceipt(row['session_id'], row['edition_id'], row['language'],
                        row['last_ordinal'], int(row['closed_tick']))


def close_session(db: sqlite3.Connection, session_id: int) -> CloseReceipt:
    sessions = SessionRepository(db)
    session = sessions.get(session_id)
    existing = get_close_receipt(db, session_id)
    if existing is not None:
        return existing
    if ContactRepository(db).active(session_id):
        raise CloseConflict('release all contacts before closing the session')

    last_ordinal = PlayRepository(db).last_ordinal(session_id)
    receipt = CloseReceipt(session_id, session.edition_id, session.language, last_ordinal, session.tick)
    db.execute(
        '''INSERT INTO close_receipts (session_id, edition_id, language, last_ordinal, closed_tick)
           VALUES (?, ?, ?, ?, ?)''',
        (receipt.session_id, receipt.edition_id, receipt.language,
         receipt.last_ordinal, str(receipt.closed_tick)),
    )
    sessions.mark_closed(session_id)
    return receipt

from dataclasses import dataclass
import sqlite3

from edition.catalog import EditionCatalog
from station.matching import match_new_contact
from station.session import SessionRepository
from station.waits import WaitRepository


class ContactConflict(ValueError):
    pass


@dataclass(frozen=True)
class Contact:
    contact_id: str
    x: int
    y: int
    tick: int


@dataclass(frozen=True)
class ContactResult:
    session_id: int
    tick: int
    event_seq: int
    active: tuple[Contact, ...]


def initialize_contact_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            session_id INTEGER NOT NULL REFERENCES sessions (session_id),
            contact_id TEXT NOT NULL,
            x TEXT NOT NULL,
            y TEXT NOT NULL,
            down_tick TEXT NOT NULL,
            released INTEGER NOT NULL DEFAULT 0 CHECK (released IN (0, 1)),
            PRIMARY KEY (session_id, contact_id)
        )
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS active_contacts
        ON contacts (session_id, contact_id) WHERE released = 0
    ''')


class ContactRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def active(self, session_id: int) -> tuple[Contact, ...]:
        rows = self.db.execute(
            '''SELECT contact_id, x, y, down_tick FROM contacts
               WHERE session_id = ? AND released = 0 ORDER BY contact_id''',
            (session_id,),
        )
        return tuple(Contact(row['contact_id'], int(row['x']), int(row['y']), int(row['down_tick']))
                     for row in rows)

    def add(self, session_id: int, contact: Contact) -> None:
        cursor = self.db.execute(
            '''INSERT INTO contacts (session_id, contact_id, x, y, down_tick)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (session_id, contact_id) DO NOTHING''',
            (session_id, contact.contact_id, str(contact.x), str(contact.y), str(contact.tick)),
        )
        if cursor.rowcount == 0:
            raise ContactConflict(f'contact ID already used: {contact.contact_id}')

    def release(self, session_id: int, contact_id: str) -> None:
        cursor = self.db.execute(
            '''UPDATE contacts SET released = 1
               WHERE session_id = ? AND contact_id = ? AND released = 0''',
            (session_id, contact_id),
        )
        if cursor.rowcount == 0:
            raise ContactConflict(f'contact is not active: {contact_id}')


def press(
    db: sqlite3.Connection, session_id: int, action: str, contact_id: str,
    tick: int, x: int | None = None, y: int | None = None,
) -> ContactResult:
    sessions = SessionRepository(db)
    session = sessions.get_open(session_id)
    if action not in ('down', 'up'):
        raise ContactConflict('action must be down or up')
    if not isinstance(contact_id, str) or not contact_id.strip():
        raise ContactConflict('contact_id must be a nonblank string')
    if action == 'down' and (type(x) is not int or type(y) is not int):
        raise ContactConflict('press coordinates must be integers')
    if action == 'up' and (x is not None or y is not None):
        raise ContactConflict('release must omit coordinates')

    session = sessions.update_clock(session, tick, contact_event=True)
    contacts = ContactRepository(db)
    waits = WaitRepository(db)
    if action == 'down':
        others = contacts.active(session_id)
        contact = Contact(contact_id, x, y, tick)
        contacts.add(session_id, contact)
        bundle = EditionCatalog(db).get(session.edition_id).bundle
        for match in match_new_contact(bundle, session.language, contact, others):
            waits.start(session_id, session.edition_id, match)
    else:
        contacts.release(session_id, contact_id)
        waits.cancel_for_contact(session_id, contact_id)
    return ContactResult(session_id, tick, session.event_seq, contacts.active(session_id))

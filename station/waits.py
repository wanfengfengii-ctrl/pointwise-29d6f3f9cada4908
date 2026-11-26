from dataclasses import dataclass
import sqlite3

from station.matching import PairMatch


@dataclass(frozen=True)
class PendingWait:
    session_id: int
    edition_id: int
    rule_id: str
    contacts: tuple[str, str]
    clip_id: int
    start_tick: int
    due_tick: int


def initialize_wait_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS waits (
            session_id INTEGER NOT NULL REFERENCES sessions (session_id),
            edition_id INTEGER NOT NULL REFERENCES editions (edition_id),
            rule_id TEXT NOT NULL,
            contact_a TEXT NOT NULL,
            contact_b TEXT NOT NULL,
            clip_id INTEGER NOT NULL REFERENCES clips (clip_id),
            start_tick TEXT NOT NULL,
            due_tick TEXT NOT NULL,
            PRIMARY KEY (session_id, edition_id, rule_id, contact_a, contact_b),
            FOREIGN KEY (session_id, contact_a) REFERENCES contacts (session_id, contact_id),
            FOREIGN KEY (session_id, contact_b) REFERENCES contacts (session_id, contact_id)
        )
    ''')


class WaitRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def start(self, session_id: int, edition_id: int, match: PairMatch) -> None:
        self.db.execute(
            '''INSERT INTO waits
               (session_id, edition_id, rule_id, contact_a, contact_b, clip_id, start_tick, due_tick)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (session_id, edition_id, match.rule.rule_id, *match.contacts, match.rule.clip_id,
             str(match.start_tick), str(match.start_tick + match.rule.wait)),
        )

    def cancel_for_contact(self, session_id: int, contact_id: str) -> None:
        self.db.execute(
            '''DELETE FROM waits WHERE session_id = ? AND (contact_a = ? OR contact_b = ?)''',
            (session_id, contact_id, contact_id),
        )

    def due(self, session_id: int, tick: int) -> list[PendingWait]:
        rows = self.db.execute('SELECT * FROM waits WHERE session_id = ?', (session_id,))
        ready = []
        for row in rows:
            deadline = int(row['due_tick'])
            if deadline <= tick:
                ready.append(PendingWait(
                    row['session_id'], row['edition_id'], row['rule_id'],
                    (row['contact_a'], row['contact_b']), row['clip_id'],
                    int(row['start_tick']), deadline,
                ))
        ready.sort(key=lambda wait: (wait.due_tick, wait.rule_id, wait.contacts))
        return ready

    def consume(self, wait: PendingWait) -> None:
        self.db.execute(
            '''DELETE FROM waits
               WHERE session_id = ? AND edition_id = ? AND rule_id = ?
                 AND contact_a = ? AND contact_b = ?''',
            (wait.session_id, wait.edition_id, wait.rule_id, *wait.contacts),
        )

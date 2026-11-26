from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class PlayRecord:
    play_id: int
    session_id: int
    edition_id: int
    rule_id: str
    contacts: tuple[str, str]
    tick: int
    clip_id: int
    ordinal: int


def initialize_play_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS plays (
            play_id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL REFERENCES sessions (session_id),
            edition_id INTEGER NOT NULL REFERENCES editions (edition_id),
            rule_id TEXT NOT NULL,
            contact_a TEXT NOT NULL,
            contact_b TEXT NOT NULL,
            tick TEXT NOT NULL,
            clip_id INTEGER NOT NULL REFERENCES clips (clip_id),
            ordinal INTEGER NOT NULL,
            UNIQUE (session_id, edition_id, rule_id, contact_a, contact_b),
            UNIQUE (session_id, ordinal),
            FOREIGN KEY (session_id, contact_a) REFERENCES contacts (session_id, contact_id),
            FOREIGN KEY (session_id, contact_b) REFERENCES contacts (session_id, contact_id)
        )
    ''')


class PlayRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def append_once(
        self, session_id: int, edition_id: int, rule_id: str,
        contacts: tuple[str, str], tick: int, clip_id: int,
    ) -> PlayRecord | None:
        first, second = sorted(contacts)
        ordinal = self.last_ordinal(session_id) + 1
        cursor = self.db.execute(
            '''INSERT INTO plays
               (session_id, edition_id, rule_id, contact_a, contact_b, tick, clip_id, ordinal)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (session_id, edition_id, rule_id, contact_a, contact_b) DO NOTHING''',
            (session_id, edition_id, rule_id, first, second, str(tick), clip_id, ordinal),
        )
        if cursor.rowcount == 0:
            return None
        return PlayRecord(cursor.lastrowid, session_id, edition_id, rule_id,
                          (first, second), tick, clip_id, ordinal)

    def list_for_session(self, session_id: int, last_ordinal: int) -> tuple[PlayRecord, ...]:
        rows = self.db.execute(
            'SELECT * FROM plays WHERE session_id = ? AND ordinal <= ? ORDER BY ordinal',
            (session_id, last_ordinal),
        )
        return tuple(
            PlayRecord(row['play_id'], row['session_id'], row['edition_id'], row['rule_id'],
                       (row['contact_a'], row['contact_b']), int(row['tick']), row['clip_id'],
                       row['ordinal'])
            for row in rows
        )

    def last_ordinal(self, session_id: int) -> int:
        row = self.db.execute(
            'SELECT COALESCE(MAX(ordinal), 0) FROM plays WHERE session_id = ?', (session_id,)
        ).fetchone()
        return row[0]

    def has_lineage_play(
        self, session_id: int, contacts: tuple[str, str], lineage_key: str
    ) -> bool:
        first, second = sorted(contacts)
        row = self.db.execute(
            '''SELECT 1
               FROM plays AS p
               JOIN rule_lineage AS l
                 ON l.edition_id = p.edition_id AND l.rule_id = p.rule_id
               WHERE p.session_id = ? AND p.contact_a = ? AND p.contact_b = ?
                 AND l.lineage_key = ?
               LIMIT 1''',
            (session_id, first, second, lineage_key),
        ).fetchone()
        return row is not None

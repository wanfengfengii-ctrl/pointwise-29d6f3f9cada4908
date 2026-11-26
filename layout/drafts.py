from dataclasses import asdict, dataclass
import json
import sqlite3

from layout.gestures import GestureRule
from layout.regions import Region


@dataclass(frozen=True)
class Draft:
    draft_id: str
    revision_id: int
    regions: tuple[Region, ...]
    rules: tuple[GestureRule, ...]


def initialize_draft_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS draft_revisions (
            revision_id INTEGER PRIMARY KEY,
            draft_id TEXT NOT NULL,
            regions_json TEXT NOT NULL,
            rules_json TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS draft_history
        ON draft_revisions (draft_id, revision_id)
    ''')


class DraftRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def _decode(row: sqlite3.Row) -> Draft:
        regions = tuple(Region(**item) for item in json.loads(row['regions_json']))
        rules = tuple(GestureRule.from_document(item) for item in json.loads(row['rules_json']))
        return Draft(row['draft_id'], row['revision_id'], regions, rules)

    def get(self, draft_id: str) -> Draft | None:
        row = self.db.execute(
            '''SELECT * FROM draft_revisions WHERE draft_id = ?
               ORDER BY revision_id DESC LIMIT 1''',
            (draft_id,),
        ).fetchone()
        return None if row is None else self._decode(row)

    def get_revision(self, revision_id: int) -> Draft:
        row = self.db.execute(
            'SELECT * FROM draft_revisions WHERE revision_id = ?', (revision_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f'unknown draft revision {revision_id}')
        return self._decode(row)

    def save_revision(
        self, draft_id: str, regions: tuple[Region, ...], rules: tuple[GestureRule, ...]
    ) -> Draft:
        cursor = self.db.execute(
            '''INSERT INTO draft_revisions (draft_id, regions_json, rules_json)
               VALUES (?, ?, ?)''',
            (draft_id, json.dumps([asdict(region) for region in regions]),
             json.dumps([asdict(rule) for rule in rules])),
        )
        return Draft(draft_id, cursor.lastrowid, regions, rules)

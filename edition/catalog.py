from dataclasses import dataclass
import sqlite3

from edition.bundle import EditionBundle, decode_bundle, encode_bundle


class UnknownEdition(LookupError):
    pass


@dataclass(frozen=True)
class IssuedEdition:
    edition_id: int
    bundle: EditionBundle


def initialize_edition_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS editions (
            edition_id INTEGER PRIMARY KEY,
            bundle_json TEXT NOT NULL
        )
    ''')


class EditionCatalog:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def append(self, bundle: EditionBundle) -> IssuedEdition:
        cursor = self.db.execute(
            'INSERT INTO editions (bundle_json) VALUES (?)', (encode_bundle(bundle),)
        )
        return IssuedEdition(cursor.lastrowid, bundle)

    def get(self, edition_id: int) -> IssuedEdition:
        row = self.db.execute(
            'SELECT bundle_json FROM editions WHERE edition_id = ?', (edition_id,)
        ).fetchone()
        if row is None:
            raise UnknownEdition(f'unknown edition {edition_id}')
        return IssuedEdition(edition_id, decode_bundle(row['bundle_json']))

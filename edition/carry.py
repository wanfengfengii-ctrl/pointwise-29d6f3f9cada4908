import json
import sqlite3
from dataclasses import dataclass


class CarryConflict(ValueError):
    """A successor issuance carry declaration is incomplete or inconsistent."""


@dataclass(frozen=True)
class CarryRecord:
    edition_id: int
    parent_edition_id: int
    region_carry: dict
    rule_carry: dict


def initialize_carry_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS edition_carry (
            edition_id INTEGER PRIMARY KEY REFERENCES editions (edition_id),
            parent_edition_id INTEGER NOT NULL REFERENCES editions (edition_id),
            region_carry_json TEXT NOT NULL,
            rule_carry_json TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS rule_lineage (
            edition_id INTEGER NOT NULL REFERENCES editions (edition_id),
            rule_id TEXT NOT NULL,
            lineage_key TEXT NOT NULL,
            PRIMARY KEY (edition_id, rule_id)
        )
    ''')


def birth_lineage_key(edition_id: int, rule_id: str) -> str:
    """Identity of a rule declared as newly built (carry value null)."""
    return f'{edition_id}:{rule_id}'


class CarryRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def save(self, record: CarryRecord) -> None:
        self.db.execute(
            '''INSERT INTO edition_carry
               (edition_id, parent_edition_id, region_carry_json, rule_carry_json)
               VALUES (?, ?, ?, ?)''',
            (record.edition_id, record.parent_edition_id,
             json.dumps(record.region_carry, ensure_ascii=False),
             json.dumps(record.rule_carry, ensure_ascii=False)),
        )

    def get(self, edition_id: int) -> CarryRecord | None:
        row = self.db.execute(
            'SELECT * FROM edition_carry WHERE edition_id = ?', (edition_id,)
        ).fetchone()
        if row is None:
            return None
        return CarryRecord(
            row['edition_id'], row['parent_edition_id'],
            json.loads(row['region_carry_json']), json.loads(row['rule_carry_json']),
        )


class LineageRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def save(self, edition_id: int, rule_id: str, lineage_key: str) -> None:
        self.db.execute(
            '''INSERT INTO rule_lineage (edition_id, rule_id, lineage_key)
               VALUES (?, ?, ?)''',
            (edition_id, rule_id, lineage_key),
        )

    def key_for(self, edition_id: int, rule_id: str) -> str:
        row = self.db.execute(
            'SELECT lineage_key FROM rule_lineage WHERE edition_id = ? AND rule_id = ?',
            (edition_id, rule_id),
        ).fetchone()
        if row is None:
            # Editions issued before lineage bookkeeping existed treat every
            # in-edition rule as its own independent identity.
            return birth_lineage_key(edition_id, rule_id)
        return row['lineage_key']

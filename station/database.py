from contextlib import contextmanager
from os import PathLike
import sqlite3

from audio.catalog import initialize_audio_schema
from edition.carry import initialize_carry_schema
from edition.catalog import initialize_edition_schema
from layout.drafts import initialize_draft_schema
from layout.proof import initialize_proof_schema
from performance.close import initialize_close_schema
from performance.records import initialize_play_schema
from station.contacts import initialize_contact_schema
from station.session import initialize_session_schema
from station.waits import initialize_wait_schema


def open_database(path: str | PathLike) -> sqlite3.Connection:
    db = sqlite3.connect(path, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys = ON')
    except BaseException:
        db.close()
        raise
    return db


@contextmanager
def request_transaction(db: sqlite3.Connection, *, write: bool):
    db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def initialize_database(db: sqlite3.Connection) -> None:
    with request_transaction(db, write=True):
        initialize_audio_schema(db)
        initialize_draft_schema(db)
        initialize_proof_schema(db)
        initialize_edition_schema(db)
        initialize_carry_schema(db)
        initialize_session_schema(db)
        initialize_contact_schema(db)
        initialize_wait_schema(db)
        initialize_play_schema(db)
        initialize_close_schema(db)

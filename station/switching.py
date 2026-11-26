import sqlite3

from edition.carry import CarryRepository
from edition.catalog import EditionCatalog
from station.reconcile import reconcile_waits
from station.session import (
    LiveSession,
    SessionConflict,
    SessionRepository,
)


class SwitchConflict(ValueError):
    pass


def switch_edition(
    db: sqlite3.Connection, session_id: int, edition_id: int, tick: int
) -> LiveSession:
    sessions = SessionRepository(db)
    # Unknown identities are 404 before any state check.
    session = sessions.get(session_id)
    target = EditionCatalog(db).get(edition_id)

    if session.closed:
        raise SessionConflict('session is closed')

    carry = CarryRepository(db).get(target.edition_id)
    if carry is None or carry.parent_edition_id != session.edition_id:
        raise SwitchConflict('target edition must be a direct successor of the in-use edition')

    if not target.bundle.rules_for_language(session.language):
        raise SwitchConflict('target edition has no rule in the session language')

    # Validates the logical clock and records the new in-use edition/tick in
    # one row update; event_seq (contact acceptance count) is untouched.
    updated = sessions.switch_edition(session, target.edition_id, tick)
    reconcile_waits(db, updated, target.bundle)
    return updated

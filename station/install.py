from dataclasses import dataclass
import sqlite3

from edition.catalog import EditionCatalog
from edition.verify import verify_bundle
from performance.close import close_session
from station.contacts import ContactRepository
from station.session import LiveSession, SessionRepository


STATION_ID = 'main'


class InstallConflict(ValueError):
    pass


@dataclass(frozen=True)
class InstallResult:
    station_id: str
    session: LiveSession


def install_layout(
    db: sqlite3.Connection, station_id: str, edition_id: int, language: str
) -> InstallResult:
    if station_id != STATION_ID:
        raise InstallConflict('unknown station')
    if not isinstance(language, str) or not language.strip():
        raise InstallConflict('language must be a nonblank string')

    sessions = SessionRepository(db)
    current = sessions.current()
    if current is not None and not current.closed and ContactRepository(db).active(current.session_id):
        raise InstallConflict('release all contacts before installing a map')

    edition = EditionCatalog(db).get(edition_id)
    verify_bundle(db, edition.bundle)
    if not edition.bundle.rules_for_language(language):
        raise InstallConflict('edition has no rule in the requested language')

    if current is not None and not current.closed:
        close_session(db, current.session_id)
    return InstallResult(station_id, sessions.open(edition.edition_id, language))

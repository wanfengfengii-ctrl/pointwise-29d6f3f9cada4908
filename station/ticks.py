from dataclasses import dataclass
import sqlite3

from edition.carry import LineageRepository
from performance.payload import PlaybackPayload
from performance.play import commit_play
from performance.records import PlayRepository
from station.session import SessionRepository
from station.waits import WaitRepository


@dataclass(frozen=True)
class AdvanceResult:
    session_id: int
    tick: int
    plays: tuple[PlaybackPayload, ...]


def advance(db: sqlite3.Connection, session_id: int, tick: int) -> AdvanceResult:
    sessions = SessionRepository(db)
    session = sessions.get_open(session_id)
    sessions.update_clock(session, tick)

    waits = WaitRepository(db)
    plays_repo = PlayRepository(db)
    lineage = LineageRepository(db)
    plays = []
    for wait in waits.due(session_id, tick):
        lineage_key = lineage.key_for(wait.edition_id, wait.rule_id)
        if plays_repo.has_lineage_play(session_id, wait.contacts, lineage_key):
            # Already spoken by this exact press pair on this carried rule;
            # settle and drop the stale eligibility without replaying.
            waits.consume(wait)
            continue
        payload = commit_play(
            db, session_id, wait.edition_id, wait.rule_id, wait.contacts, tick, wait.clip_id
        )
        waits.consume(wait)
        if payload is not None:
            plays.append(payload)
    return AdvanceResult(session_id, tick, tuple(plays))

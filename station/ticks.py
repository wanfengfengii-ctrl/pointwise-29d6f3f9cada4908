from dataclasses import dataclass
import sqlite3

from performance.payload import PlaybackPayload
from performance.play import commit_play
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
    plays = []
    for wait in waits.due(session_id, tick):
        payload = commit_play(
            db, session_id, wait.edition_id, wait.rule_id, wait.contacts, tick, wait.clip_id
        )
        waits.consume(wait)
        if payload is not None:
            plays.append(payload)
    return AdvanceResult(session_id, tick, tuple(plays))

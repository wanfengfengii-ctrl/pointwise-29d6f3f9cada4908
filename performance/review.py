from dataclasses import dataclass
import sqlite3

from audio.retrieve import retrieve_clip
from performance.close import CloseReceipt, get_close_receipt
from performance.payload import PlaybackPayload, build_playback_payload
from performance.records import PlayRepository
from station.session import SessionRepository


class ReviewPending(ValueError):
    pass


@dataclass(frozen=True)
class SessionReview:
    receipt: CloseReceipt
    plays: tuple[PlaybackPayload, ...]


def review_session(db: sqlite3.Connection, session_id: int) -> SessionReview:
    SessionRepository(db).get(session_id)
    receipt = get_close_receipt(db, session_id)
    if receipt is None:
        raise ReviewPending('close the session before reviewing it')
    records = PlayRepository(db).list_for_session(session_id, receipt.last_ordinal)
    plays = tuple(build_playback_payload(record, retrieve_clip(db, record.clip_id)) for record in records)
    return SessionReview(receipt, plays)

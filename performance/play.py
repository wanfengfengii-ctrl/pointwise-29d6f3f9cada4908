import sqlite3

from audio.retrieve import retrieve_clip
from performance.payload import PlaybackPayload, build_playback_payload
from performance.records import PlayRepository


def commit_play(
    db: sqlite3.Connection, session_id: int, edition_id: int, rule_id: str,
    contacts: tuple[str, str], tick: int, clip_id: int,
) -> PlaybackPayload | None:
    clip = retrieve_clip(db, clip_id)
    record = PlayRepository(db).append_once(session_id, edition_id, rule_id, contacts, tick, clip_id)
    if record is None:
        return None
    return build_playback_payload(record, clip)

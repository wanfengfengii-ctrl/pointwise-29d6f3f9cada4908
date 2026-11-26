import sqlite3

from audio.catalog import AudioCatalog
from audio.content import Clip


class UnknownClip(LookupError):
    pass


def retrieve_clip(db: sqlite3.Connection, clip_id: int) -> Clip:
    clip = AudioCatalog(db).get(clip_id)
    if clip is None:
        raise UnknownClip(f'unknown clip {clip_id}')
    return clip

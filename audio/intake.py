import sqlite3

from audio.catalog import AudioCatalog
from audio.content import Clip, validate_clip_content


def register_clip(db: sqlite3.Connection, data: dict) -> Clip:
    language, text, duration, source = validate_clip_content(data)
    return AudioCatalog(db).append(language, text, duration, source)

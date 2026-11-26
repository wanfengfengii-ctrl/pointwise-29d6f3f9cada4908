import sqlite3

from audio.content import Clip, ClipSource


def initialize_audio_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS clips (
            clip_id INTEGER PRIMARY KEY,
            language TEXT NOT NULL,
            text TEXT NOT NULL,
            duration TEXT NOT NULL,
            exhibit TEXT NOT NULL,
            material_id TEXT NOT NULL
        )
    ''')


class AudioCatalog:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def append(self, language: str, text: str, duration: int, source: ClipSource) -> Clip:
        cursor = self.db.execute(
            '''INSERT INTO clips (language, text, duration, exhibit, material_id)
               VALUES (?, ?, ?, ?, ?)''',
            (language, text, str(duration), source.exhibit, source.material_id),
        )
        return Clip(cursor.lastrowid, language, text, duration, source)

    def get(self, clip_id: int) -> Clip | None:
        row = self.db.execute(
            'SELECT * FROM clips WHERE clip_id = ?', (str(clip_id),)
        ).fetchone()
        if row is None:
            return None
        source = ClipSource(row['exhibit'], row['material_id'])
        return Clip(row['clip_id'], row['language'], row['text'], int(row['duration']), source)

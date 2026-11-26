import sqlite3

from audio.retrieve import UnknownClip, retrieve_clip
from edition.bundle import EditionBundle


class InvalidEditionBundle(ValueError):
    pass


def verify_bundle(db: sqlite3.Connection, bundle: EditionBundle) -> None:
    languages = {}
    for rule in bundle.rules:
        if rule.clip_id not in languages:
            try:
                languages[rule.clip_id] = retrieve_clip(db, rule.clip_id).language
            except UnknownClip as error:
                raise InvalidEditionBundle(f'{rule.rule_id} refers to a missing clip') from error
        if languages[rule.clip_id] != rule.language:
            raise InvalidEditionBundle(f'{rule.rule_id} refers to a clip in another language')

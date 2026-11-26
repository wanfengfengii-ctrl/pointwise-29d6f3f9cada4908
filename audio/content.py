from dataclasses import dataclass


class InvalidClip(ValueError):
    pass


@dataclass(frozen=True)
class ClipSource:
    exhibit: str
    material_id: str


@dataclass(frozen=True)
class Clip:
    clip_id: int
    language: str
    text: str
    duration: int
    source: ClipSource


def validate_clip_content(data: dict) -> tuple[str, str, int, ClipSource]:
    for field in ('exhibit', 'language', 'text', 'material_id'):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise InvalidClip(f'{field} must be a nonblank string')

    duration = data.get('duration')
    if type(duration) is not int or duration <= 0:
        raise InvalidClip('duration must be a positive integer')

    source = ClipSource(exhibit=data['exhibit'], material_id=data['material_id'])
    return data['language'], data['text'], duration, source

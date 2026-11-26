from dataclasses import asdict, dataclass

from audio.content import Clip, ClipSource
from performance.records import PlayRecord


@dataclass(frozen=True)
class PlaybackPayload(PlayRecord):
    text: str
    duration: int
    source: ClipSource


def build_playback_payload(record: PlayRecord, clip: Clip) -> PlaybackPayload:
    if record.clip_id != clip.clip_id:
        raise ValueError('play record and clip do not have the same clip ID')
    return PlaybackPayload(**asdict(record), text=clip.text, duration=clip.duration, source=clip.source)

from dataclasses import asdict, dataclass
import json

from layout.gestures import GestureRule
from layout.regions import Region


@dataclass(frozen=True)
class EditionBundle:
    proof_id: int
    regions: tuple[Region, ...]
    rules: tuple[GestureRule, ...]

    def region_at(self, x: int, y: int) -> Region | None:
        for region in self.regions:
            if region.contains(x, y):
                return region
        return None

    def rules_for_language(self, language: str) -> tuple[GestureRule, ...]:
        return tuple(rule for rule in self.rules if rule.language == language)


def encode_bundle(bundle: EditionBundle) -> str:
    return json.dumps(asdict(bundle), separators=(',', ':'))


def decode_bundle(text: str) -> EditionBundle:
    data = json.loads(text)
    return EditionBundle(
        proof_id=data['proof_id'],
        regions=tuple(Region(**item) for item in data['regions']),
        rules=tuple(GestureRule.from_document(item) for item in data['rules']),
    )

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from edition.bundle import EditionBundle
from layout.gestures import GestureRule, rule_key

if TYPE_CHECKING:
    from station.contacts import Contact


@dataclass(frozen=True)
class PairMatch:
    rule: GestureRule
    contacts: tuple[str, str]
    start_tick: int


def match_new_contact(
    bundle: EditionBundle,
    language: str,
    new_contact: Contact,
    other_contacts: tuple[Contact, ...],
) -> tuple[PairMatch, ...]:
    new_region = bundle.region_at(new_contact.x, new_contact.y)
    if new_region is None:
        return ()
    rules = {rule_key(language, *rule.regions): rule for rule in bundle.rules_for_language(language)}
    matches = []
    for other in other_contacts:
        region = bundle.region_at(other.x, other.y)
        if region is None or region.region_id == new_region.region_id:
            continue
        rule = rules.get(rule_key(language, new_region.region_id, region.region_id))
        if rule is None:
            continue
        first, second = sorted((new_contact.contact_id, other.contact_id))
        matches.append(PairMatch(rule, (first, second), max(new_contact.tick, other.tick)))
    return tuple(matches)

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


def resolve_pair(
    bundle: EditionBundle,
    language: str,
    contact_a: Contact,
    contact_b: Contact,
) -> tuple[GestureRule, tuple[str, str]] | None:
    """Resolve one actual press pair against a map.

    Returns the rule and canonically ordered contact IDs when the two fixed
    coordinates land in distinct regions bound by a language rule.
    """
    region_a = bundle.region_at(contact_a.x, contact_a.y)
    region_b = bundle.region_at(contact_b.x, contact_b.y)
    if region_a is None or region_b is None or region_a.region_id == region_b.region_id:
        return None
    rules = {rule_key(language, *rule.regions): rule
             for rule in bundle.rules_for_language(language)}
    rule = rules.get(rule_key(language, region_a.region_id, region_b.region_id))
    if rule is None:
        return None
    return rule, tuple(sorted((contact_a.contact_id, contact_b.contact_id)))


def match_new_contact(
    bundle: EditionBundle,
    language: str,
    new_contact: Contact,
    other_contacts: tuple[Contact, ...],
) -> tuple[PairMatch, ...]:
    matches = []
    for other in other_contacts:
        resolved = resolve_pair(bundle, language, new_contact, other)
        if resolved is None:
            continue
        rule, contacts = resolved
        matches.append(PairMatch(
            rule, contacts, max(new_contact.tick, other.tick)
        ))
    return tuple(matches)

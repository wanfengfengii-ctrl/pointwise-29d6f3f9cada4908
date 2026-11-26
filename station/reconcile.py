from dataclasses import dataclass
import sqlite3

from edition.bundle import EditionBundle
from edition.carry import LineageRepository
from performance.records import PlayRepository
from station.contacts import ContactRepository
from station.matching import PairMatch, resolve_pair
from station.session import LiveSession
from station.waits import PendingWait, WaitRepository


@dataclass(frozen=True)
class ReconcileReport:
    retained: tuple[PendingWait, ...]
    started: tuple[PairMatch, ...]
    terminated: tuple[PendingWait, ...]


def reconcile_waits(
    db: sqlite3.Connection, session: LiveSession, bundle: EditionBundle
) -> ReconcileReport:
    """Re-judge every held press pair against the just-switched map.

    A pending wait whose rule keeps the same carried lineage keeps its
    original start tick and is re-keyed to the live edition/rule. A mismatch
    terminates the wait. A restored or brand-new match starts at the switch
    tick, unless that exact press pair already spoke the rule lineage once.
    """
    session_id = session.session_id
    switch_tick = session.tick
    contacts = ContactRepository(db).active(session_id)
    waits = WaitRepository(db)
    lineage = LineageRepository(db)
    plays = PlayRepository(db)

    previous_by_pair: dict[tuple[str, str], list[PendingWait]] = {}
    for wait in waits.list_all(session_id):
        previous_by_pair.setdefault(tuple(sorted(wait.contacts)), []).append(wait)

    retained = []
    started = []
    terminated = []

    for index in range(len(contacts)):
        for other_index in range(index + 1, len(contacts)):
            pair = tuple(sorted((contacts[index].contact_id,
                                 contacts[other_index].contact_id)))
            previous = previous_by_pair.pop(pair, [])
            resolved = resolve_pair(bundle, session.language,
                                     contacts[index], contacts[other_index])

            if resolved is None:
                # Mismatch ends this stretch of waiting.
                for old in previous:
                    waits.consume(old)
                    terminated.append(old)
                continue

            rule, pair = resolved
            current_key = lineage.key_for(session.edition_id, rule.rule_id)

            if plays.has_lineage_play(session_id, pair, current_key):
                # The same actual press pair already opened this carried rule;
                # mismatch and restoration never restore eligibility.
                for old in previous:
                    waits.consume(old)
                    terminated.append(old)
                continue

            same_lineage = [
                old for old in previous
                if lineage.key_for(old.edition_id, old.rule_id) == current_key
            ]
            # Every prior row is settled; at most one exists in normal flows.
            for old in previous:
                waits.consume(old)
                if old not in same_lineage:
                    terminated.append(old)

            if same_lineage:
                # Continuously valid carried rule: preserve the earliest
                # original wait start, settling against current identities.
                start_tick = min(old.start_tick for old in same_lineage)
                match = PairMatch(rule, pair, start_tick)
                waits.start(session_id, session.edition_id, match)
                retained.extend(same_lineage)
            else:
                # No prior wait, or a different (newly built) rule identity:
                # the wait is newly established at the switch tick.
                match = PairMatch(rule, pair, switch_tick)
                waits.start(session_id, session.edition_id, match)
                started.append(match)

    # Any wait whose pair is no longer fully held is stale; releases normally
    # remove these already, but never carry an old-edition wait past a switch.
    for leftovers in previous_by_pair.values():
        for old in leftovers:
            waits.consume(old)
            terminated.append(old)

    return ReconcileReport(tuple(retained), tuple(started), tuple(terminated))

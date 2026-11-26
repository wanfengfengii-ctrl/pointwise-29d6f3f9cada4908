from dataclasses import dataclass
import sqlite3

from audio.retrieve import UnknownClip, retrieve_clip
from layout.drafts import Draft, DraftRepository
from layout.gestures import GestureRule, RuleConflict, validate_rules
from layout.regions import Region, RegionConflict, validate_regions


class ProofConflict(ValueError):
    def __init__(self, position: str, message: str):
        super().__init__(message)
        self.position = position


class UnknownProof(LookupError):
    pass


@dataclass(frozen=True)
class ProofSnapshot:
    proof_id: int
    draft_id: str
    regions: tuple[Region, ...]
    rules: tuple[GestureRule, ...]


def initialize_proof_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS proofs (
            proof_id INTEGER PRIMARY KEY REFERENCES draft_revisions (revision_id)
        )
    ''')


def _snapshot(draft: Draft) -> ProofSnapshot:
    return ProofSnapshot(draft.revision_id, draft.draft_id, draft.regions, draft.rules)


def create_proof(
    db: sqlite3.Connection, draft_id: str, regions: object, rules: object
) -> ProofSnapshot:
    if not isinstance(draft_id, str) or not draft_id.strip():
        raise ProofConflict('draft_id', 'draft_id must be a nonblank string')

    try:
        checked_regions = validate_regions(regions)
        checked_rules = validate_rules(rules, {region.region_id for region in checked_regions})
    except (RegionConflict, RuleConflict) as error:
        raise ProofConflict(error.position, str(error)) from error

    for index, rule in enumerate(checked_rules):
        position = f'rules[{index}].clip_id'
        try:
            clip = retrieve_clip(db, rule.clip_id)
        except UnknownClip as error:
            raise ProofConflict(position, str(error)) from error
        if clip.language != rule.language:
            raise ProofConflict(position, 'clip language differs from rule language')

    draft = DraftRepository(db).save_revision(draft_id, checked_regions, checked_rules)
    db.execute('INSERT INTO proofs (proof_id) VALUES (?)', (draft.revision_id,))
    return _snapshot(draft)


def get_proof(db: sqlite3.Connection, proof_id: int) -> ProofSnapshot:
    row = db.execute('SELECT proof_id FROM proofs WHERE proof_id = ?', (proof_id,)).fetchone()
    if row is None:
        raise UnknownProof(f'unknown proof {proof_id}')
    return _snapshot(DraftRepository(db).get_revision(proof_id))

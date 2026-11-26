import sqlite3

from edition.bundle import EditionBundle
from edition.carry import (
    CarryConflict,
    CarryRecord,
    CarryRepository,
    LineageRepository,
    birth_lineage_key,
)
from edition.catalog import EditionCatalog, IssuedEdition
from edition.verify import verify_bundle
from layout.proof import get_proof


def _record_fresh_lineage(db: sqlite3.Connection, issued: IssuedEdition) -> None:
    lineage = LineageRepository(db)
    for rule in issued.bundle.rules:
        lineage.save(issued.edition_id, rule.rule_id,
                     birth_lineage_key(issued.edition_id, rule.rule_id))


def issue_layout(db: sqlite3.Connection, proof_id: int) -> IssuedEdition:
    proof = get_proof(db, proof_id)
    bundle = EditionBundle(proof.proof_id, proof.regions, proof.rules)
    verify_bundle(db, bundle)
    issued = EditionCatalog(db).append(bundle)
    _record_fresh_lineage(db, issued)
    return issued


def _validate_category_carry(declaration: object, new_ids: set[str],
                             parent_ids: set[str], category: str) -> dict:
    if not isinstance(declaration, dict):
        raise CarryConflict(f'{category}_carry must be an object keyed by new {category} IDs')
    if set(declaration.keys()) != new_ids:
        raise CarryConflict(
            f'{category}_carry must declare every new {category} exactly once'
        )
    carried_sources: dict[str, str] = {}
    for new_id, source_id in declaration.items():
        if source_id is None:
            continue
        if not isinstance(source_id, str) or source_id not in parent_ids:
            raise CarryConflict(
                f'{category}_carry[{new_id}] references an unknown parent {category}'
            )
        if source_id in carried_sources:
            raise CarryConflict(
                f'parent {category} {source_id} is carried by both '
                f'{carried_sources[source_id]} and {new_id}'
            )
        carried_sources[source_id] = new_id
    return declaration


def issue_successor(
    db: sqlite3.Connection,
    proof_id: int,
    parent_edition_id: int,
    region_carry: object,
    rule_carry: object,
) -> tuple[IssuedEdition, CarryRecord]:
    # Resolve both fixed identities first so unknown proof/edition numbers
    # surface as 404 before declaration conflicts.
    proof = get_proof(db, proof_id)
    parent = EditionCatalog(db).get(parent_edition_id)

    bundle = EditionBundle(proof.proof_id, proof.regions, proof.rules)
    verify_bundle(db, bundle)

    new_regions = {region.region_id: region for region in bundle.regions}
    parent_regions = {region.region_id: region for region in parent.bundle.regions}
    region_decl = _validate_category_carry(
        region_carry, set(new_regions), set(parent_regions), 'region'
    )

    new_rules = {rule.rule_id: rule for rule in bundle.rules}
    parent_rules = {rule.rule_id: rule for rule in parent.bundle.rules}
    rule_decl = _validate_category_carry(
        rule_carry, set(new_rules), set(parent_rules), 'rule'
    )

    # A carried narration rule keeps one identity only when both endpoints are
    # carried regions and the unordered endpoint pair, language, fixed clip and
    # wait beats are identical to the parent rule.
    for new_rule_id, parent_rule_id in rule_decl.items():
        if parent_rule_id is None:
            continue
        new_rule = new_rules[new_rule_id]
        parent_rule = parent_rules[parent_rule_id]
        mapped_endpoints = []
        for endpoint in new_rule.regions:
            parent_region_id = region_decl[endpoint]
            if parent_region_id is None:
                raise CarryConflict(
                    f'rule {new_rule_id} cannot carry {parent_rule_id}: '
                    'both endpoint regions must be carried'
                )
            mapped_endpoints.append(parent_region_id)
        if sorted(mapped_endpoints) != sorted(parent_rule.regions):
            raise CarryConflict(
                f'rule {new_rule_id} endpoints do not match parent rule {parent_rule_id}'
            )
        if (new_rule.language != parent_rule.language
                or new_rule.clip_id != parent_rule.clip_id
                or new_rule.wait != parent_rule.wait):
            raise CarryConflict(
                f'rule {new_rule_id} does not match carry conditions of {parent_rule_id}'
            )

    issued = EditionCatalog(db).append(bundle)

    lineage = LineageRepository(db)
    for rule in bundle.rules:
        parent_rule_id = rule_decl[rule.rule_id]
        if parent_rule_id is None:
            lineage_key = birth_lineage_key(issued.edition_id, rule.rule_id)
        else:
            lineage_key = lineage.key_for(parent.edition_id, parent_rule_id)
        lineage.save(issued.edition_id, rule.rule_id, lineage_key)

    record = CarryRecord(
        issued.edition_id, parent.edition_id, dict(region_decl), dict(rule_decl)
    )
    CarryRepository(db).save(record)
    return issued, record

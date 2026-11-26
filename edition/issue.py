import sqlite3

from edition.bundle import EditionBundle
from edition.catalog import EditionCatalog, IssuedEdition
from edition.verify import verify_bundle
from layout.proof import get_proof


def issue_layout(db: sqlite3.Connection, proof_id: int) -> IssuedEdition:
    proof = get_proof(db, proof_id)
    bundle = EditionBundle(proof.proof_id, proof.regions, proof.rules)
    verify_bundle(db, bundle)
    return EditionCatalog(db).append(bundle)

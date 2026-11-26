import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from demo import CLIPS, contact_input, gesture, install_input, proof_input, rectangle, running_station
from station.http import serve


def expect_equal(actual, expected):
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def proof(client, clip_id, left, right, rule, x0, x1):
    data = proof_input(clip_id, regions=[rectangle(left, x0, x1), rectangle(right, 4, 6)],
                       rules=[gesture(clip_id, rule_id=rule, endpoints=(left, right))])
    return client.expect("POST", "/proofs", data, status=201)["proof_id"]


def issue(client, proof_id, **carry):
    return client.expect("POST", "/editions", {"proof_id": proof_id, **carry}, status=201)["edition_id"]


def begin(client, edition):
    session = client.expect("POST", "/station/install", install_input(edition), status=201)["session"]
    path = "/sessions/{}".format(session["session_id"])
    press(client, path, "down", "A", 1, 1)
    press(client, path, "down", "B", 1, 5)
    return path, session


def press(client, path, action, finger, tick, x=None):
    return client.expect("POST", path + "/contacts", contact_input(action, finger, tick, x, 1))


def advance(client, path, tick):
    return client.expect("POST", path + "/advance", {"tick": tick})["plays"]


def switch(client, path, session, edition, tick):
    actual = client.expect("POST", path + "/switch-edition", {"edition_id": edition, "tick": tick})
    expect_equal(actual, {**session, "edition_id": edition, "tick": tick, "event_seq": 2})


def play_facts(events):
    return [[p["edition_id"], p["rule_id"], p["contacts"], p["tick"], p["source"]["material_id"]]
            for p in events]


def fixture(client, base, base_proof, clip_id):
    shifted = issue(client, proof(client, clip_id, "shifted", "right", "shift-rule", 2, 4))
    path, _ = begin(client, base)
    rejection = client.expect("POST", "/station/install", install_input(shifted), status=409)
    expect_equal(rejection["error"], "install_conflict")
    expect_equal(advance(client, path, 4), [])
    plays = play_facts(advance(client, path, 5))
    expect_equal(plays, [[base, "r01", ["A", "B"], 5, CLIPS["A"]["material_id"]]])
    expect_equal(client.expect("GET", f"/editions/{base}")["proof_id"], base_proof)
    print(json.dumps({"blocked_ordinary_install": rejection["error"], "actual_plays": plays},
                     ensure_ascii=False))


def live_case(client, base, base_proof, clip_id):
    continued = issue(client, proof(client, clip_id, "entry", "exit", "guide-rule", 0, 3),
                      parent_edition_id=base, region_carry={"entry": "L", "exit": "R"},
                      rule_carry={"guide-rule": "r01"})
    shifted = issue(client, proof(client, clip_id, "shifted", "right", "shift-rule", 2, 4),
                    parent_edition_id=continued, region_carry={"shifted": "entry", "right": "exit"},
                    rule_carry={"shift-rule": "guide-rule"})
    restored = issue(client, base_proof, parent_edition_id=shifted,
                     region_carry={"L": "shifted", "R": "right"}, rule_carry={"r01": "shift-rule"})
    path, session = begin(client, base)
    switch(client, path, session, continued, 3)
    expect_equal(advance(client, path, 4), [])
    first = advance(client, path, 5)
    expect_equal(play_facts(first), [[continued, "guide-rule", ["A", "B"], 5, CLIPS["A"]["material_id"]]])
    switch(client, path, session, shifted, 6)
    switch(client, path, session, restored, 7)
    return path, first, restored


def finish_live_case(client, path, first, restored):
    held = advance(client, path, 11)
    expect_equal(held, [])
    press(client, path, "up", "A", 12)
    press(client, path, "down", "D", 12, 1)
    expect_equal(advance(client, path, 15), [])
    second = advance(client, path, 16)
    expect_equal(play_facts(second), [[restored, "r01", ["B", "D"], 16, CLIPS["A"]["material_id"]]])
    press(client, path, "up", "B", 16)
    press(client, path, "up", "D", 16)
    receipt = client.expect("POST", path + "/close", {})
    expect_equal(receipt["edition_id"], restored)
    expect_equal(receipt["last_ordinal"], 2)
    review = client.expect("GET", path + "/review")
    expect_equal(review, {"receipt": receipt, "plays": first + second})
    print(json.dumps({"held_at_11": held, "review": review}, ensure_ascii=False))


def example(mode):
    with TemporaryDirectory() as directory:
        database = Path(directory) / "station.sqlite3"
        with running_station(database) as client:
            clip_id = client.expect("POST", "/clips", CLIPS["A"], status=201)["clip_id"]
            base_proof = proof(client, clip_id, "L", "R", "r01", 0, 2)
            base = issue(client, base_proof)
            if mode == "fixture":
                fixture(client, base, base_proof, clip_id)
                return
            state = live_case(client, base, base_proof, clip_id)
        with running_station(database) as client:
            finish_live_case(client, *state)


def main():
    parser = argparse.ArgumentParser(description="Touch map edition exercise")
    commands = parser.add_subparsers(dest="mode", required=True)
    commands.add_parser("fixture")
    commands.add_parser("demo")
    launch = commands.add_parser("serve")
    launch.add_argument("--host", choices=["127.0.0.1"], required=True)
    launch.add_argument("--port", type=int, required=True)
    launch.add_argument("--db", default="touch_station.sqlite3")
    options = parser.parse_args()
    if options.mode == "serve":
        serve(options.db, options.port)
    else:
        example(options.mode)


if __name__ == "__main__":
    main()

"""Single verification entry: original regression plus live-map checks.

Runs, in order and from the repository root:
  1. check_project.py          - the original unittest regression suite
  2. demo.py                   - the original ordinary staging scenario
  3. live_map_example.py fixture - hands-on install rejection / old map deadline
  4. live_map_example.py demo    - carried-edition switch drill

Every stage is a real entry point whose process exit code reports success.
This wrapper exits non-zero if any stage fails.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STAGES = (
    ('regression', [sys.executable, '-B', 'check_project.py']),
    ('ordinary-demo', [sys.executable, '-B', 'demo.py']),
    ('live-map-fixture', [sys.executable, '-B', 'live_map_example.py', 'fixture']),
    ('live-map-demo', [sys.executable, '-B', 'live_map_example.py', 'demo']),
)


def main() -> int:
    failures = []
    for name, argv in STAGES:
        print(f'\n===== VERIFY STAGE: {name} =====', flush=True)
        result = subprocess.run(argv, cwd=ROOT)
        if result.returncode != 0:
            failures.append((name, result.returncode))
            print(f'----- stage {name!r} failed with {result.returncode} -----',
                  file=sys.stderr, flush=True)

    if failures:
        print('VERIFY_ALL FAIL: ' + ', '.join(
            f'{name}(exit {code})' for name, code in failures), file=sys.stderr)
        return 1
    print('VERIFY_ALL PASS: regression, ordinary demo, fixture and live-map demo')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

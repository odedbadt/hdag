"""
Snapshot test: for each tests/fixtures/<name>.json, build the DOT source via
render_hdag.build_dot() and compare against tests/fixtures/<name>.dot.

Run:    python tests/test_render.py
Update: python tests/test_render.py --update    (rewrites .dot snapshots)
"""
import difflib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from render_hdag import build_dot, build_global_dag

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def dot_for(json_path):
    with open(json_path) as f:
        hdag = json.load(f)
    nodes, edges, cluster = build_global_dag(hdag)
    return build_dot(nodes, edges, cluster).source


def check_sentinel_collision_raises():
    """Composite that shares a name with a child (and no sentinel override) must fail."""
    bad = {
        "children": {
            "X": {
                "children": {"X": {}, "y": {}},
                "dag": [
                    ["X->inputs->p",  "X->inputs->q"],
                    ["X->outputs->r", "X->outputs->s"]
                ]
            }
        },
        "dag": [["root->inputs->in", "X->inputs->p"]]
    }
    try:
        build_global_dag(bad)
    except ValueError as e:
        if "collide" in str(e).lower() or "sentinel" in str(e).lower():
            return True
        print(f"FAIL     collision: wrong ValueError message: {e}")
        return False
    print("FAIL     collision: build_global_dag did not raise on parent/child name collision")
    return False


def main(update=False):
    pairs = sorted(FIXTURES.glob("*.json"))
    if not pairs:
        print(f"No fixtures found in {FIXTURES}")
        return 1

    failures = 0
    for json_path in pairs:
        dot_path = json_path.with_suffix(".dot")
        actual = dot_for(json_path)

        if update:
            dot_path.write_text(actual)
            print(f"updated  {dot_path.name}")
            continue

        if not dot_path.exists():
            print(f"MISSING  {dot_path.name} (run with --update)")
            failures += 1
            continue

        expected = dot_path.read_text()
        if actual == expected:
            print(f"ok       {json_path.name}")
        else:
            failures += 1
            print(f"FAIL     {json_path.name}")
            diff = difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=str(dot_path),
                tofile="actual",
            )
            sys.stdout.writelines(diff)

    if not update:
        if check_sentinel_collision_raises():
            print("ok       sentinel-collision raises")
        else:
            failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main(update="--update" in sys.argv))

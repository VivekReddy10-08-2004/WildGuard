"""Local/offline foundation commands; deliberately has no network acquisition."""

import argparse
import json
from pathlib import Path

from scripts.wildlife_audio.manifest import legacy_records
from scripts.wildlife_audio.rights import bundle_redistribution_errors
from scripts.wildlife_audio.schema import validate_bundle, validate_inventory
from scripts.wildlife_audio.storage import Inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "audit", "recover"):
        cmd = sub.add_parser(name)
        cmd.add_argument("root", type=Path)
    for name in ("validate", "export-legacy"):
        cmd = sub.add_parser(name)
        cmd.add_argument("bundle", type=Path, help="JSON object keyed by schema kind")
        cmd.add_argument(
            "--sources", type=Path, default=Path("data/datasets/audio/sources.json")
        )
        cmd.add_argument(
            "--redistributable",
            action="store_true",
            help="require recording-level commercial rights reviews",
        )
        cmd.add_argument(
            "--audio-root",
            type=Path,
            help="reconcile assets against an existing managed inventory",
        )
    args = parser.parse_args()
    if args.command in {"validate", "export-legacy"}:
        tables = json.loads(args.bundle.read_text("utf-8"))
        registry = json.loads(args.sources.read_text("utf-8"))
        if not isinstance(tables, dict):
            parser.error("bundle must be an object")
        errors = validate_bundle(tables, {s["id"] for s in registry["sources"]})
        if not errors and args.redistributable:
            errors.extend(bundle_redistribution_errors(tables))
        if not errors and args.audio_root is not None:
            if not (args.audio_root / "state/inventory.sqlite3").is_file():
                errors.append("audio-root must contain an existing inventory")
            else:
                errors.extend(validate_inventory(tables, Inventory(args.audio_root)))
        if args.command == "export-legacy" and not errors:
            for row in legacy_records(tables, {s["id"] for s in registry["sources"]}):
                print(json.dumps(row, sort_keys=True, allow_nan=False))
            return 0
        print(json.dumps({"errors": errors}, indent=2))
        return int(bool(errors))
    inventory = Inventory(args.root)
    recovered = inventory.recover() if args.command == "recover" else []
    print(json.dumps({"recovered": recovered, **inventory.audit()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

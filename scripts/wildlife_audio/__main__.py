"""Wildlife audio engineering: offline analysis and explicitly approved acquisition."""

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
    cmd = sub.add_parser(
        "acquire", help="requires exact-file approval and retained rights evidence"
    )
    cmd.add_argument("root", type=Path)
    cmd.add_argument("spec", type=Path)
    cmd.add_argument("--approval", type=Path, required=True)
    cmd.add_argument("--rights", type=Path, required=True)
    cmd = sub.add_parser(
        "analyze", help="offline decoding, duplicates, taxonomy and split QC"
    )
    cmd.add_argument("root", type=Path)
    cmd.add_argument("catalog", type=Path)
    cmd.add_argument(
        "--taxonomy",
        type=Path,
        default=Path("data/datasets/audio/taxonomy_snapshot.json"),
    )
    cmd.add_argument("--save-relative", default=None)
    cmd = sub.add_parser(
        "diagnose", help="offline strict multi-decoder review of retained MP3 originals"
    )
    cmd.add_argument("root", type=Path)
    cmd.add_argument("bundle", type=Path)
    cmd.add_argument("--mpg123", type=Path, required=True)
    cmd.add_argument("--report-relative", required=True)
    cmd.add_argument(
        "--apply",
        action="store_true",
        help="explicitly apply retained, consensus-checked states",
    )
    args = parser.parse_args()
    if args.command == "diagnose":
        from scripts.wildlife_audio.diagnostics import (
            apply_retained_diagnosis,
            diagnose,
            retain_diagnosis,
        )

        inventory = Inventory(args.root)
        bundle = json.loads(args.bundle.read_text("utf-8"))
        report = diagnose(
            inventory,
            [a["path"] for a in bundle["asset"] if a["kind"] == "original"],
            args.mpg123,
        )
        saved = retain_diagnosis(inventory, report, args.report_relative)
        if args.apply:
            apply_retained_diagnosis(inventory, saved["path"])
        print(
            json.dumps(
                {
                    "report": saved,
                    "counts": report["counts"],
                    "states_applied": args.apply,
                },
                indent=2,
            )
        )
        return int(report["counts"]["quarantined"] + report["counts"]["rejected"] > 0)
    if args.command == "acquire":
        from scripts.wildlife_audio.download import DownloadSpec, acquire

        result = acquire(
            DownloadSpec(**json.loads(args.spec.read_text("utf-8"))),
            Inventory(args.root),
            json.loads(args.approval.read_text("utf-8")),
            json.loads(args.rights.read_text("utf-8")),
        )
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "analyze":
        from scripts.wildlife_audio.pipeline import analyze, retain_report

        inventory = Inventory(args.root)
        report = analyze(
            json.loads(args.catalog.read_text("utf-8")),
            inventory,
            json.loads(args.taxonomy.read_text("utf-8")),
        )
        if args.save_relative:
            retain_report(report, inventory, args.save_relative)
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
        return int(bool(report["failures"]))
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

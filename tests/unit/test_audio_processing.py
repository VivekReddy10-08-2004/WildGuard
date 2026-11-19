"""Network-free tests with synthetic signals and mocked HTTP responses."""

import csv
import hashlib
import io
import json
import sqlite3
import urllib.error
import zipfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from scripts.wildlife_audio.adapters import nps_spec, pnw_spec
from scripts.wildlife_audio.annotations import (
    canonical_annotation,
    nps_clip,
    pnw_record_identity,
    pnw_test2,
)
from scripts.wildlife_audio.archive import inspect_zip, retain_metadata
from scripts.wildlife_audio.dedup import (
    acoustic_candidate,
    duplicate_edges,
    fingerprint,
)
from scripts.wildlife_audio.download import DownloadSpec, acquire, check_url, open_https
from scripts.wildlife_audio.integrity import AudioError, decode_audio
from scripts.wildlife_audio.pipeline import analyze, retain_report
from scripts.wildlife_audio.schema import validate
from scripts.wildlife_audio.splits import group_and_split
from scripts.wildlife_audio.storage import BudgetExceeded, Inventory, InventoryError
from scripts.wildlife_audio.taxonomy import normalize


def snapshot():
    return json.loads(
        Path("data/datasets/audio/taxonomy_snapshot.json").read_text("utf-8")
    )


class Response(io.BytesIO):
    def __init__(self, data, headers=None, status=200):
        super().__init__(data)
        self.headers = headers or {}
        self.status = status


def request_fixture(tmp_path):
    inv = Inventory(tmp_path / "inventory", 1000)
    evidence = inv.put(
        "evidence/license.txt", [b"test-evidence"], 13, {"kind": "synthetic"}
    )
    spec = DownloadSpec(
        "nps_sound_gallery",
        "test.mp3",
        "https://www.nps.gov/nps-audiovideo/test.mp3",
        "original/test.mp3",
        3,
    )
    approval = {"url": spec.url, "expected_bytes": 3, "approved": True}
    rights = {
        "source_id": spec.source_id,
        "source_recording_id": spec.source_recording_id,
        "url": spec.url,
        "download_permitted": True,
        "reviewed_by": "synthetic-test",
        "evidence": [{"path": evidence["path"], "sha256": evidence["sha256"]}],
    }
    return inv, spec, approval, rights


def test_bounded_acquisition(tmp_path):
    inv, spec, approval, rights = request_fixture(tmp_path)
    digest = hashlib.sha256(b"abc").hexdigest()
    result = acquire(
        replace(spec, sha256=digest),
        inv,
        approval,
        rights,
        lambda *args: Response(b"abc", {"Content-Length": "3"}),
    )
    assert result["sha256"] == digest
    assert inv.audit()["actual_bytes"] == 16


def test_reservation_precedes_network_read(tmp_path):
    inv, spec, approval, rights = request_fixture(tmp_path)

    def transport(*args):
        with sqlite3.connect(inv.state / "inventory.sqlite3") as db:
            row = db.execute(
                "SELECT state,reserved FROM assets WHERE path=?", (spec.path,)
            ).fetchone()
            assert row == ("pending", 3)
        return Response(b"abc")

    acquire(spec, inv, approval, rights, transport)


def test_budget_rejection_precedes_network(tmp_path):
    inv, spec, approval, rights = request_fixture(tmp_path)
    inv.put("full", [b"x" * 987], 987, {"kind": "synthetic"})

    def never(*args):
        raise AssertionError("network contacted with no free budget")

    with pytest.raises(BudgetExceeded):
        acquire(spec, inv, approval, rights, never)


def test_redirect_target_checked_before_contact(monkeypatch):
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(
                request.full_url,
                302,
                "redirect",
                {"Location": "https://evil.test/audio"},
                None,
            )

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    with pytest.raises(ValueError):
        open_https("https://www.nps.gov/a", {"www.nps.gov"})
    assert calls == ["https://www.nps.gov/a"]


@pytest.mark.parametrize(
    "fault", ["approval", "url", "size", "rights", "evidence", "reviewer"]
)
def test_missing_authorization_stops_before_network(tmp_path, fault):
    inv, spec, approval, rights = request_fixture(tmp_path)
    if fault == "approval":
        approval["approved"] = False
    elif fault == "url":
        approval["url"] = "https://www.nps.gov/other"
    elif fault == "size":
        approval["expected_bytes"] = 4
    elif fault == "rights":
        rights["download_permitted"] = False
    elif fault == "reviewer":
        rights["reviewed_by"] = None
    else:
        rights["evidence"][0]["sha256"] = "0" * 64

    def never(*args):
        raise AssertionError("network was contacted")

    with pytest.raises(PermissionError):
        acquire(spec, inv, approval, rights, never)


@pytest.mark.parametrize(
    "body,headers,status,error",
    [
        (b"ab", {}, 200, InventoryError),
        (b"abcd", {}, 200, BudgetExceeded),
        (b"abc", {"Content-Length": "4"}, 200, InventoryError),
        (b"abc", {"Content-Encoding": "gzip"}, 200, InventoryError),
        (b"abc", {}, 206, InventoryError),
    ],
)
def test_http_failure_keeps_counted_quarantine(tmp_path, body, headers, status, error):
    inv, spec, approval, rights = request_fixture(tmp_path)
    with pytest.raises(error):
        acquire(
            spec, inv, approval, rights, lambda *args: Response(body, headers, status)
        )
    row = next(r for r in inv.audit()["assets"] if r["path"] == spec.path)
    assert row["state"] == "quarantined"
    assert inv.audit()["actual_bytes"] <= inv.cap


def test_md5_and_etag_mismatch(tmp_path):
    inv, spec, approval, rights = request_fixture(tmp_path)
    spec = replace(spec, md5="0" * 32)
    with pytest.raises(InventoryError, match="MD5"):
        acquire(spec, inv, approval, rights, lambda *args: Response(b"abc"))
    spec = replace(spec, path="other", etag='"etag"', md5=None)
    with pytest.raises(InventoryError, match="ETag"):
        acquire(
            spec,
            inv,
            approval,
            rights,
            lambda *args: Response(b"abc", {"ETag": "changed"}),
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://www.nps.gov/x",
        "https://evil.test/x",
        "https://www.nps.gov@evil.test/x",
        "https://user@www.nps.gov/x",
        "https://www.nps.gov:444/x",
    ],
)
def test_https_source_host_validation(url):
    with pytest.raises(ValueError):
        check_url(url, {"www.nps.gov"})


def test_nps_adapter():
    assert (
        nps_spec(
            {"audio_url": "https://www.nps.gov/a.mp3", "size_bytes": 3}
        ).expected_bytes
        == 3
    )
    with pytest.raises(ValueError):
        nps_spec({"audio_url": "https://www.nps.gov/a.wav", "size_bytes": 3})


def test_pinned_zenodo_adapter():
    release = {
        "metadata": {"doi": "10.5281/zenodo.17955691"},
        "files": [
            {
                "key": "Test_Set_2.zip",
                "size": 7515853849,
                "checksum": "md5:" + "0" * 32,
                "links": {"self": "https://zenodo.org/a.zip"},
            }
        ],
    }
    assert pnw_spec(release, "Test_Set_2.zip").expected_bytes == 7515853849
    with pytest.raises(ValueError):
        pnw_spec(release, "Test_Set_1.zip")


def tone(rate=16000, seconds=4, frequency=700):
    t = np.arange(rate * seconds) / rate
    return (
        0.3
        * np.sin(2 * np.pi * (frequency * t + 120 * t * t))
        * (0.65 + 0.35 * np.sin(2 * np.pi * 3 * t))
    ).astype("float32")


@pytest.mark.parametrize(
    "format,suffix", [("WAV", "wav"), ("FLAC", "flac"), ("OGG", "ogg"), ("MP3", "mp3")]
)
def test_full_decode_supported_formats(tmp_path, format, suffix):
    file = tmp_path / f"a.{suffix}"
    sf.write(file, tone(), 16000, format=format)
    info = decode_audio(file, hashlib.sha256(file.read_bytes()).hexdigest())
    assert info["frames"] > 0
    assert 3.8 < info["duration_seconds"] < 4.2
    assert info["channels"] == 1
    with pytest.raises(AudioError, match="SHA"):
        decode_audio(file, "0" * 64)


@pytest.mark.parametrize(
    "failure", ["garbage", "empty", "truncated", "nonfinite", "duration"]
)
def test_decode_failures(tmp_path, failure):
    file = tmp_path / "bad.wav"
    if failure == "garbage":
        file.write_bytes(b"not audio")
    elif failure == "empty":
        sf.write(file, np.zeros(0), 16000)
    elif failure == "nonfinite":
        sf.write(file, np.array([np.nan, np.inf]), 16000, subtype="FLOAT")
    else:
        sf.write(file, tone(), 16000)
        if failure == "truncated":
            file.write_bytes(file.read_bytes()[:-100])
    with pytest.raises((AudioError, ValueError)):
        decode_audio(file, max_seconds=1 if failure == "duration" else 3600)


def test_exact_and_acoustic_duplicates(tmp_path):
    a, b, c, d = [tmp_path / n for n in ["a.wav", "b.flac", "c.wav", "d.wav"]]
    signal = tone(seconds=6)
    sf.write(a, signal, 16000, subtype="PCM_16")
    pcm, rate = sf.read(a, dtype="int16")
    sf.write(b, pcm, rate, subtype="PCM_16")
    sf.write(c, signal[16000:] * 0.7, 16000, subtype="FLOAT")
    sf.write(d, tone(seconds=6, frequency=3500), 16000)
    fa, fb, fc, fd = [fingerprint(p) for p in [a, b, c, d]]
    assert fa["pcm_sha256"] == fb["pcm_sha256"]
    assert acoustic_candidate(fa, fc) is not None
    assert acoustic_candidate(fa, fd) is None
    edges = duplicate_edges({"a": fa, "b": fb, "c": fc})
    assert any(e["reason"] == "decoded_pcm" for e in edges)
    assert any(e["reason"] == "acoustic" for e in edges)


def test_silence_and_ultrasound_profile(tmp_path):
    file = tmp_path / "silence.wav"
    sf.write(file, np.zeros(32000), 16000)
    first = fingerprint(file)
    assert acoustic_candidate(first, first) is None
    assert "silent" in first["flags"]
    file = tmp_path / "bat.wav"
    sf.write(file, tone(rate=96000, frequency=22000), 96000)
    second = fingerprint(file)
    assert second["profile"] == "ultrasound-native-96000"
    assert acoustic_candidate(first, second) is None


def test_taxonomy_unknown_higher_rank_and_synonym():
    s = snapshot()
    assert normalize("CALA1", s)["scientific_name"] == "Canis latrans"
    assert (
        normalize("Rana catesbeiana", s)["scientific_name"] == "Lithobates catesbeianus"
    )
    assert normalize("Deer snort", s)["rank"] == "genus"
    assert normalize("Crickets", s)["scientific_name"] is None
    assert normalize("Fly", s)["scientific_name"] is None
    assert normalize("unidentified bat", s)["status"] == "unknown"
    assert normalize(None, s)["status"] == "unknown"
    s["taxa"].append({**s["taxa"][0], "taxon_id": "other"})
    assert normalize("Coyote", s)["status"] == "ambiguous"


def write_pnw(tmp_path, manual="CALA1", offset="3"):
    file = tmp_path / "labels.csv"
    with file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "FOLDER",
                "IN_FILE",
                "CHANNEL",
                "OFFSET",
                "DURATION",
                "TOP1MATCH",
                "TOP1DIST",
                "MANUAL_ID",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "FOLDER": "clips/CALA1",
                "IN_FILE": "Loc_0001_20230101_000000_part_001.wav",
                "CHANNEL": "0",
                "OFFSET": offset,
                "DURATION": "12",
                "TOP1MATCH": "CALA1",
                "TOP1DIST": "0.9",
                "MANUAL_ID": manual,
            }
        )
    return file


@pytest.mark.parametrize("manual,present", [("CALA1", True), ("No", False)])
def test_pnw_preserves_review_scope(tmp_path, manual, present):
    imported = pnw_test2(write_pnw(tmp_path, manual))[0]
    assert imported["focal_present"] is present
    assert imported["original_annotation"]["MANUAL_ID"] == manual
    assert imported["source_split"] == "test"
    assert imported["start_seconds"] == 3 and imported["end_seconds"] == 15
    assert imported["confidence"] is None
    canonical = canonical_annotation(
        imported, "r", "a", "p", normalize("CALA1", snapshot())
    )
    assert validate("annotation", canonical) == []
    if not present:
        assert canonical["taxon_id"] is None
    identity = pnw_record_identity(imported)
    assert identity["site_id"] == "Loc_0001"
    assert identity["source_split"] == "test"
    assert identity["recordist_id"] is None


@pytest.mark.parametrize(
    "manual,offset", [("Other", "3"), ("CALA1", "nan"), ("CALA1", "-1")]
)
def test_pnw_rejects_unreviewed_semantics(tmp_path, manual, offset):
    with pytest.raises(ValueError):
        pnw_test2(write_pnw(tmp_path, manual, offset))


def test_nps_weak_annotation():
    row = nps_clip("Crickets", "https://www.nps.gov/page")
    assert row["start_seconds"] is None
    assert row["confidence"] is None
    assert row["verification"] == "unverified"


def recording(rid, **kw):
    return {
        "recording_id": rid,
        "source_id": "source",
        "source_recording_id": rid,
        "site_id": rid,
        "session_id": rid,
        "recordist_id": rid,
        **kw,
    }


def test_connected_group_and_official_holdout():
    records = [
        recording("a"),
        recording("b", site_id="a"),
        recording("c", source_split="test"),
    ]
    split = group_and_split(records, [{"left": "b", "right": "c"}])
    assert {r["split"] for r in split} == {"test"}
    assert len({r["group_id"] for r in split}) == 1
    assert split == group_and_split(
        list(reversed(records)), [{"left": "b", "right": "c"}]
    )


def test_official_conflict_and_unknown_group():
    records = [
        recording("a", source_split="train"),
        recording("b", source_split="test"),
    ]
    assert {
        r["split"] for r in group_and_split(records, [{"left": "a", "right": "b"}])
    } == {"excluded"}
    assert (
        group_and_split([recording("unknown", site_id=None)])[0]["split"]
        == "unassigned"
    )


def test_source_parent_and_recordist_linkage():
    records = [
        recording("a"),
        recording("b", parent_recording_ids=["a"]),
        recording("c", recordist_id="b"),
    ]
    assert len({r["group_id"] for r in group_and_split(records)}) == 1
    with pytest.raises(ValueError):
        group_and_split([recording("x", parent_recording_ids=["missing"])])


@pytest.mark.parametrize("name", ["../bad.txt", "/bad.txt", "C:/bad.txt"])
def test_archive_path_rejection(tmp_path, name):
    file = tmp_path / "a.zip"
    with zipfile.ZipFile(file, "w") as z:
        z.writestr(name, "abc")
    with pytest.raises(ValueError):
        inspect_zip(file)


def test_bounded_metadata_extraction(tmp_path):
    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("README.md", "abc")
        z.writestr("a.wav", b"xyz")
    inv = Inventory(tmp_path / "inventory", 10)
    retain_metadata(archive, ["README.md"], inv, "repo")
    assert inv.audit()["actual_bytes"] == 3
    with pytest.raises(ValueError):
        retain_metadata(archive, ["a.wav"], inv, "repo")
    with pytest.raises(ValueError):
        retain_metadata(archive, ["README.md"], inv, "other", max_member_bytes=2)


def test_offline_pipeline_and_report(tmp_path):
    file = tmp_path / "test.wav"
    sf.write(file, tone(), 16000)
    inv = Inventory(tmp_path / "inventory", 1_000_000)
    data = file.read_bytes()
    inv.put("original/a.wav", [data], len(data), {"source": "synthetic"})
    r = recording("a", path="original/a.wav", original_labels=["Coyote"])
    report = analyze({"recordings": [r]}, inv, snapshot())
    assert report["failures"] == []
    assert report["release_ready"] is False
    assert report["recordings"][0]["commercial_redistribution_errors"]
    retain_report(report, inv, "reports/qc.json")
    assert inv.audit()["actual_bytes"] > len(data)
    r["source_id"] = "pnw_cnet_v5"
    r["source_split"] = "train"
    with pytest.raises(ValueError, match="evaluation"):
        analyze({"recordings": [r]}, inv, snapshot())


def test_pnw_official_split_guard_at_grouping_api():
    with pytest.raises(ValueError, match="protected evaluation"):
        group_and_split(
            [recording("pnw", source_id="pnw_cnet_v5", source_split="train")]
        )


def test_qc_marks_incomplete_duplicate_audit(tmp_path, monkeypatch):
    file = tmp_path / "audio.wav"
    sf.write(file, tone(), 16000)
    inv = Inventory(tmp_path / "inventory", 1_000_000)
    data = file.read_bytes()
    inv.put("a.wav", [data], len(data), {"source": "synthetic"})

    def fail(*args):
        raise ValueError("alignment bound exceeded")

    monkeypatch.setattr("scripts.wildlife_audio.pipeline.duplicate_edges", fail)
    report = analyze(
        {"recordings": [recording("a", path="a.wav", original_labels=[])]},
        inv,
        snapshot(),
    )
    assert report["failures"]
    assert report["splits"][0]["split"] == "excluded"


def test_report_size_bound(tmp_path):
    inv = Inventory(tmp_path / "inventory", 10)
    with pytest.raises(ValueError, match="allowance"):
        retain_report({"test": "x" * 100}, inv, "report.json", max_bytes=10)
    assert inv.audit()["actual_bytes"] == 0


def test_unsupported_codec_and_decode_limits(tmp_path):
    file = tmp_path / "a.aiff"
    sf.write(file, tone(), 16000, format="AIFF")
    with pytest.raises(AudioError, match="unsupported"):
        decode_audio(file)
    with pytest.raises(AudioError, match="bounds"):
        decode_audio(file, max_seconds=float("nan"))


def test_committed_pilot_has_no_audio_approval():
    report = json.loads(
        Path("data/datasets/audio/pilot_acquisition_report.json").read_text("utf-8")
    )
    assert sum(e["spec"]["expected_bytes"] for e in report["downloads"]) == 2_193_880
    assert all(e["approval"]["approved"] is False for e in report["downloads"])
    assert report["pnw"]["test_set_2_downloaded"] is False


def test_annotations_validated_against_actual_decoded_audio(tmp_path):
    file = tmp_path / "a.wav"
    sf.write(file, tone(), 16000)
    inv = Inventory(tmp_path / "inventory", 1_000_000)
    data = file.read_bytes()
    inv.put("a.wav", [data], len(data), {"source": "synthetic"})
    imported = nps_clip("Coyotes", "https://www.nps.gov/page")
    annotation = canonical_annotation(
        imported, "a", "a", "provenance", normalize("Coyotes", snapshot())
    )
    catalog = {
        "recordings": [recording("a", path="a.wav", original_labels=["Coyotes"])],
        "annotations": [annotation],
    }
    report = analyze(catalog, inv, snapshot())
    assert report["annotations"] == [annotation]
    assert report["failures"] == []
    annotation.update(annotation_type="window", start_seconds=0, end_seconds=5)
    report = analyze(catalog, inv, snapshot())
    assert report["failures"]
    assert report["splits"][0]["split"] == "excluded"

# Local/offline wildlife audio storage foundation

Core storage foundation on `ram_audio`; no model execution is included. For
explicit acquisition and offline audio analysis, see
[audio_dataset_processing.md](audio_dataset_processing.md).
Python 3.12 is required. From the repository root:

```powershell
python -m pip install -r requirements-audio-foundation.txt
$env:WILDGUARD_AUDIO_ROOT = 'D:\WildGuardAudio'
python -m scripts.wildlife_audio init $env:WILDGUARD_AUDIO_ROOT
python -m scripts.wildlife_audio audit $env:WILDGUARD_AUDIO_ROOT
python -m scripts.wildlife_audio recover $env:WILDGUARD_AUDIO_ROOT
```

POSIX shells can use `export WILDGUARD_AUDIO_ROOT=/mnt/ssd/wildguard-audio`.
Commands take the root explicitly; no implicit fallback into the repository.
Use a dedicated local SSD outside Git, OneDrive and other synchronization folders.
Do not create the root inside a symlink, junction or shared/network filesystem.
Initialization creates only `payload/` and `state/` in an otherwise empty directory.

## Accounting and admission

The immutable maximum is **30,000,000,000 bytes**, decimal GB. A root may be
initialized through the Python API with a smaller cap, never a larger one.
Every retained original, processed copy, compressed archive, partial download,
quarantined file, source annotation and provenance evidence belongs in `payload/`.
All payload bytes count, regardless of filename extension. Keeping a ZIP and its
extracted contents consumes both sizes. Processed copies consume additional space.

`state/` contains only the SQLite inventory and its bounded operational lock/journal
files; it is not an alternative media store. SQLite control overhead is outside
the payload cap and requires additional free disk space. No claim is made that
the entire physical filesystem, SQLite overhead included, is under 30 GB.

All writers must use `Inventory.put(relative_path, chunks, max_bytes, provenance,
expected_sha256=None)`. `chunks` yields bytes; callers must provide a conservative
upper bound even when a server omits its content length. Network handling is in the
separate bounded download adapter. Example using synthetic data:

```python
from pathlib import Path
from scripts.wildlife_audio.storage import Inventory

inventory = Inventory(Path(r'D:\WildGuardAudio'))
inventory.put('examples/synthetic.txt', [b'example'], 7,
              {'source_id': 'synthetic-example'})
print(inventory.audit())
```

One operating-system lock covers reconciliation, reservation and streaming.
A concurrent writer fails rather than competing for capacity. Durable SQLite
intent precedes file creation. Each chunk is checked before writing, the file
is flushed/fsynced, and final size/SHA-256 is committed. The unused reservation
is then released. A source checksum mismatch is a failed acquisition, with its
retained bytes quarantined and still counted.

Before each write, audit checks every registered hash and reconciles directory
contents. Unknown, missing, resized, linked or altered files block writes.
Windows drive paths, UNC paths, alternate streams, device names, traversal,
symlinks, junctions and hard links are rejected. Portable manifest paths use `/`.

## Crash recovery and ownership assumptions

After interruption run `recover`, followed by `audit`. Pending files are retained
as quarantined with measured bytes and hashes; missing pending files receive an
empty quarantined placeholder. Recovery never assumes a completed download and
never deletes source data. Running recovery again is safe. Tampered ready files,
unknown files and partials larger than their reservation require investigation;
recovery does not silently bless those conditions.

The root must be writable only by the trusted dataset owner and managed pipeline.
Path checks are not a sandbox against a hostile process swapping filesystem
objects during a write. Audit detects unmanaged changes, but cannot prevent an
unrelated program writing arbitrary bytes. Power-loss recovery is conservative:
missing or damaged accepted files fail validation; recovery does not promise
physical-media durability beyond the operating system/filesystem guarantees.

Only **one authoritative dataset root** is supported in this stage. Do not create
additional audio caches, copies, backups or cloud replicas outside its ledger.
An external backup or remote backend is not exempt from the overall retained-audio
budget; such replication must remain disabled until a shared accounting mechanism
is implemented. There is no remote backend, bulk-audio extraction utility or
deletion API yet.
Future extraction must use the same bounded writer and reject unsafe member paths.

## Git and offline operation

GitHub holds schemas, source research, code, policies and permitted metadata.
Audio, local inventory, credentials, detailed sensitive locations and permission
documents stay external. Do not use Git LFS for this pilot. Runtime validation,
inventory, hashing and recovery work offline after dependency installation.
The standalone pinned requirements avoid installing CUDA/model dependencies;
the existing `pyproject.toml` and `uv.lock` are unchanged.

Run tests with `python -m pip install pytest==9.2.0`, then
`python -m pytest tests/unit tests/integration -q`.

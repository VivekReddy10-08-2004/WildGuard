"""Single-writer, crash-recoverable payload inventory with a decimal 30 GB cap.

All retained media, archives, partials and processed copies must live in payload/.
The local owner must prevent other programs from writing into this managed root.
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from scripts.wildlife_audio.paths import safe_path

CAP_BYTES = 30_000_000_000


class InventoryError(RuntimeError):
    """Storage is inconsistent; stop writes and investigate."""


class BudgetExceeded(InventoryError):
    """A reservation or write would exceed its budget."""


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def exclusive_lock(path: Path):
    """OS-released lock; a process crash cannot leave a stale ownership marker."""
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class Inventory:
    """Use put() for every byte, including provenance and retained ZIP archives.

    Reservations are persisted before file creation. Failed writes remain counted
    as quarantined payload; recover() retains interrupted writes, never deletes.
    A smaller immutable cap may be chosen for a pilot or test.
    """

    def __init__(self, root: Path, cap_bytes: int = CAP_BYTES):
        if type(cap_bytes) is not int or not 0 < cap_bytes <= CAP_BYTES:
            raise ValueError("cap must be an integer in 1..30,000,000,000")
        self.root = Path(root).absolute()
        safe_path(self.root, "payload")
        self.root.mkdir(parents=True, exist_ok=True)
        self.payload = safe_path(self.root, "payload")
        self.payload.mkdir(exist_ok=True)
        self.state = safe_path(self.root, "state")
        self.state.mkdir(exist_ok=True)
        self.cap = cap_bytes
        with self._db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise InventoryError("unsupported inventory schema version")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (cap INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS assets (
                    path TEXT PRIMARY KEY COLLATE NOCASE,
                    state TEXT NOT NULL
                        CHECK(state IN ('pending','ready','quarantined')),
                    reserved INTEGER NOT NULL CHECK(reserved >= 0),
                    size INTEGER NOT NULL CHECK(size >= 0),
                    sha256 TEXT,
                    expected_sha256 TEXT,
                    provenance TEXT NOT NULL
                );
            """)
            row = db.execute("SELECT cap FROM settings").fetchone()
            if row is None:
                db.execute("INSERT INTO settings VALUES (?)", (cap_bytes,))
            elif row[0] != cap_bytes:
                raise InventoryError(
                    "stored cap differs; do not silently change budgets"
                )
            db.execute("PRAGMA user_version=1")

    @contextmanager
    def _db(self):
        for name in (
            "state/inventory.lock",
            "state/inventory.sqlite3",
            "state/inventory.sqlite3-journal",
        ):
            safe_path(self.root, name)
        with exclusive_lock(self.state / "inventory.lock"):
            # Control directory is not a second media store.
            allowed = {
                "inventory.lock",
                "inventory.sqlite3",
                "inventory.sqlite3-journal",
            }
            if any(p.name not in allowed for p in self.state.iterdir()):
                raise InventoryError("unexpected file in control directory")
            if any(p.name not in {"payload", "state"} for p in self.root.iterdir()):
                raise InventoryError("unexpected file outside payload")
            db = sqlite3.connect(self.state / "inventory.sqlite3", timeout=0)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def _audit(self, db, allow_pending=False):
        rows = {r["path"]: dict(r) for r in db.execute("SELECT * FROM assets")}
        found = set()

        def scan_error(error):
            raise error

        for directory, dirs, files in os.walk(
            self.payload, followlinks=False, onerror=scan_error
        ):
            for name in dirs + files:
                rel = (Path(directory) / name).relative_to(self.payload).as_posix()
                safe_path(self.payload, rel)
            for name in files:
                rel = (Path(directory) / name).relative_to(self.payload).as_posix()
                if rel not in rows:
                    raise InventoryError(f"untracked payload: {rel}")
                found.add(rel)
        committed = 0
        actual = 0
        for rel, row in rows.items():
            file = safe_path(self.payload, rel)
            if file.exists() and not file.is_file():
                raise InventoryError(f"not a regular file: {rel}")
            size = file.stat().st_size if rel in found else 0
            actual += size
            if row["state"] == "pending":
                if not allow_pending:
                    raise InventoryError(
                        "interrupted write; run recover before writing"
                    )
                if size > row["reserved"]:
                    raise InventoryError("partial exceeds reservation")
                committed += row["reserved"]
            else:
                if rel not in found or size != row["size"]:
                    raise InventoryError(f"missing or resized payload: {rel}")
                if sha256_file(file) != row["sha256"]:
                    raise InventoryError(f"checksum mismatch: {rel}")
                committed += size
        if committed > self.cap or actual > self.cap:
            raise BudgetExceeded("managed payload exceeds cap")
        return {
            "cap_bytes": self.cap,
            "actual_bytes": actual,
            "committed_bytes": committed,
            "available_bytes": self.cap - committed,
            "assets": list(rows.values()),
        }

    def audit(self):
        """Full hash and filesystem reconciliation; fails closed on discrepancies."""
        with self._db() as db:
            return self._audit(db)

    def put(self, relative, chunks, max_bytes, provenance, expected_sha256=None):
        """Retain a bounded byte stream; never overwrite an asset or invent metadata.

        Callers supply an upper bound even when the server omits Content-Length.
        A checksum mismatch quarantines the bytes rather than accepting the file.
        This is storage admission, not authorization for dataset redistribution.
        """
        if type(max_bytes) is not int or not 0 <= max_bytes <= self.cap:
            raise BudgetExceeded("invalid reservation size")
        if expected_sha256 is not None and not re.fullmatch(
            r"[0-9a-f]{64}", expected_sha256
        ):
            raise ValueError("expected SHA-256 must be lowercase hexadecimal")
        if not isinstance(provenance, dict) or not provenance:
            raise ValueError("nonempty provenance object required")
        provenance_json = json.dumps(provenance, sort_keys=True, allow_nan=False)
        destination = safe_path(self.payload, relative)
        with self._db() as db:
            status = self._audit(db)
            if max_bytes > status["available_bytes"]:
                raise BudgetExceeded("reservation exceeds available bytes")
            if max_bytes > shutil.disk_usage(self.root).free:
                raise BudgetExceeded("insufficient filesystem space for reservation")
            if db.execute("SELECT 1 FROM assets WHERE path=?", (relative,)).fetchone():
                raise InventoryError("asset already inventoried")
            if destination.exists():
                raise InventoryError("destination already exists")
            db.execute(
                "INSERT INTO assets VALUES (?, 'pending', ?, 0, NULL, ?, ?)",
                (relative, max_bytes, expected_sha256, provenance_json),
            )
            db.commit()  # Durable intent before creating any payload bytes.
            size = 0
            digest = hashlib.sha256()
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                safe_path(self.payload, relative)
                with destination.open("xb") as stream:
                    for chunk in chunks:
                        if not isinstance(chunk, bytes):
                            raise TypeError("stream must yield bytes")
                        if size + len(chunk) > max_bytes:
                            raise BudgetExceeded("stream exceeds reservation")
                        stream.write(chunk)
                        size += len(chunk)
                        digest.update(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                if (
                    expected_sha256 is not None
                    and digest.hexdigest() != expected_sha256
                ):
                    raise InventoryError("source checksum mismatch")
                db.execute(
                    "UPDATE assets SET state='ready', size=?, reserved=?, sha256=? "
                    "WHERE path=?",
                    (size, size, digest.hexdigest(), relative),
                )
                db.commit()
            except BaseException:
                # Inspect actual bytes, including a short/failed OS write.
                if destination.is_file():
                    size = destination.stat().st_size
                    checksum = sha256_file(destination)
                    db.execute(
                        "UPDATE assets SET state='quarantined', size=?, reserved=?, "
                        "sha256=? WHERE path=?",
                        (size, size, checksum, relative),
                    )
                    db.commit()
                # A missing file leaves pending intent for explicit recovery.
                raise
            self._audit(db)
            return {"path": relative, "size_bytes": size, "sha256": digest.hexdigest()}

    def recover(self):
        """Retain interrupted files as quarantined; release only unused reservations.

        No guessed success and no deletion. Existing accepted assets are verified
        first. Missing pending files become zero-byte quarantined placeholders.
        """
        with self._db() as db:
            self._audit(db, allow_pending=True)
            recovered = []
            for row in db.execute(
                "SELECT * FROM assets WHERE state='pending'"
            ).fetchall():
                file = safe_path(self.payload, row["path"])
                if not file.exists():
                    file.parent.mkdir(parents=True, exist_ok=True)
                    with file.open("xb") as stream:
                        stream.flush()
                        os.fsync(stream.fileno())
                size = file.stat().st_size
                db.execute(
                    "UPDATE assets SET state='quarantined', size=?, reserved=?, "
                    "sha256=? WHERE path=?",
                    (size, size, sha256_file(file), row["path"]),
                )
                recovered.append(row["path"])
            db.commit()
            self._audit(db)
            return recovered

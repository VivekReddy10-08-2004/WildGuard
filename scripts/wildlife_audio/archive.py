"""Inspect ZIP metadata and retain selected small non-audio members safely."""

import stat
import zipfile

from scripts.wildlife_audio.paths import safe_path


def inspect_zip(archive, max_entries=100_000):
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        if len(members) > max_entries:
            raise ValueError("too many ZIP entries")
        names = set()
        result = []
        for info in members:
            relative = info.filename.rstrip("/")
            safe_path(archive.parent, relative)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("ZIP symlink rejected")
            if relative.casefold() in names:
                raise ValueError("duplicate ZIP member")
            names.add(relative.casefold())
            result.append(
                {
                    "name": info.filename,
                    "size_bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                    "crc32": info.CRC,
                }
            )
        return result


def retain_metadata(archive, names, inventory, prefix, max_member_bytes=10_000_000):
    """No extractall, no overwrite, no audio extraction through this entry point."""
    inspect_zip(archive)
    result = []
    with zipfile.ZipFile(archive) as zipped:
        for name in names:
            info = zipped.getinfo(name)
            suffix = name.rsplit(".", 1)[-1].lower()
            if suffix not in {
                "md",
                "txt",
                "csv",
                "tsv",
                "json",
                "py",
                "r",
                "yaml",
                "yml",
            }:
                raise ValueError("only reviewed metadata member types are permitted")
            if info.is_dir() or info.file_size > max_member_bytes:
                raise ValueError("metadata member exceeds bound")
            with zipped.open(info) as stream:

                def chunks(stream=stream):
                    while chunk := stream.read(64 * 1024):
                        yield chunk

                result.append(
                    inventory.put(
                        f"{prefix}/{name}",
                        chunks(),
                        info.file_size,
                        {"archive": str(archive.name), "member": name},
                    )
                )
    return result

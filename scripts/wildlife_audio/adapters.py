"""NPS direct-media and pinned Zenodo-release spec adapters (no discovery scrape)."""

from urllib.parse import urlsplit

from scripts.wildlife_audio.download import DownloadSpec


def nps_spec(entry):
    url = entry["audio_url"]
    name = urlsplit(url).path.rsplit("/", 1)[-1]
    if not name.lower().endswith(".mp3"):
        raise ValueError("NPS pilot adapter expects original MP3")
    spec = DownloadSpec(
        "nps_sound_gallery",
        name,
        url,
        f"originals/nps/{name}",
        entry["size_bytes"],
        etag=entry.get("etag"),
    )
    spec.validate()
    return spec


def pnw_spec(release, filename):
    if release.get("metadata", {}).get("doi") != "10.5281/zenodo.17955691":
        raise ValueError("adapter requires pinned PNW v5 release")
    if filename not in {"v5_Repo_Files.zip", "Test_Set_2.zip"}:
        raise ValueError("file not enabled for this source adapter")
    file = next(f for f in release["files"] if f["key"] == filename)
    algorithm, checksum = file["checksum"].split(":", 1)
    if algorithm != "md5":
        raise ValueError("unexpected publisher checksum")
    spec = DownloadSpec(
        "pnw_cnet_v5",
        filename,
        file["links"]["self"],
        f"archives/pnw-v5/{filename}",
        file["size"],
        md5=checksum,
    )
    spec.validate()
    return spec

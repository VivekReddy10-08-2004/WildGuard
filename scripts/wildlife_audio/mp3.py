"""Conservative Layer III framing/CRC checks. Never resynchronize over damage."""

import mmap
from pathlib import Path


def crc16(data):
    """MPEG audio CRC-16, polynomial 0x8005, initial value 0xffff."""
    crc = 0xFFFF
    for value in data:
        for bit in range(7, -1, -1):
            carry = ((crc >> 15) & 1) ^ ((value >> bit) & 1)
            crc = (crc << 1) & 0xFFFF
            if carry:
                crc ^= 0x8005
    return crc


def _bits(data, offset, count):
    value = int.from_bytes(data, "big")
    return (value >> (len(data) * 8 - offset - count)) & ((1 << count) - 1)


def scan_mp3(path, max_seconds=3600):
    """Check contiguous frames, protected side info and structural sample count.

    Does not decode Huffman data: a strict decoder remains mandatory. Unknown
    trailers/metadata and free-format streams fail rather than being skipped.
    """
    path = Path(path)
    if path.stat().st_size == 0:
        raise ValueError("empty MP3")
    with (
        path.open("rb") as stream,
        mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data,
    ):
        size = len(data)
        offset = 0
        tags = []
        if data[:3] == b"ID3":
            if (
                size < 10
                or data[3] not in {2, 3, 4}
                or any(v & 128 for v in data[6:10])
            ):
                raise ValueError("invalid ID3 header")
            length = 10 + sum(data[6 + i] << (21 - 7 * i) for i in range(4))
            if data[3] == 4 and data[5] & 16:
                length += 10
            if length > size or length > 10_000_000:
                raise ValueError("truncated or over-limit ID3 metadata")
            tags.append({"kind": "ID3v2", "offset": 0, "bytes": length})
            offset = length
        start = offset
        end = size
        if size >= 128 and data[-128:-125] == b"TAG":
            end -= 128
            tags.append({"kind": "ID3v1", "offset": end, "bytes": 128})
        frames = protected = samples = previous_slots = 0
        rate = channels = version = None
        timing_header = False
        while offset < end:
            if offset + 4 > end:
                raise ValueError(f"truncated MP3 header at byte {offset}")
            header = int.from_bytes(data[offset : offset + 4], "big")
            ver, layer = (header >> 19) & 3, (header >> 17) & 3
            bitrate_index, rate_index = (header >> 12) & 15, (header >> 10) & 3
            if (
                header >> 21 != 2047
                or ver == 1
                or layer != 1
                or bitrate_index in {0, 15}
                or rate_index == 3
            ):
                raise ValueError(
                    f"invalid MP3 frame header at byte {offset}; resync forbidden"
                )
            this_rate = [44100, 48000, 32000][rate_index] // {3: 1, 2: 2, 0: 4}[ver]
            this_channels = 1 if (header >> 6) & 3 == 3 else 2
            if frames and (this_rate, this_channels, ver) != (rate, channels, version):
                raise ValueError("MP3 stream changes rate/channels/version")
            rate, channels, version = this_rate, this_channels, ver
            bitrates = (
                [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
                if ver == 3
                else [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
            )
            length = (144000 if ver == 3 else 72000) * bitrates[
                bitrate_index
            ] // rate + ((header >> 9) & 1)
            if offset + length > end:
                raise ValueError(f"truncated MP3 frame at byte {offset}")
            has_crc = not bool((header >> 16) & 1)
            info_length = (
                (17 if channels == 1 else 32)
                if ver == 3
                else (9 if channels == 1 else 17)
            )
            info_start = offset + 4 + (2 if has_crc else 0)
            side = data[info_start : info_start + info_length]
            if len(side) != info_length or info_start + info_length > offset + length:
                raise ValueError("truncated MP3 side information")
            if has_crc:
                stored = int.from_bytes(data[offset + 4 : offset + 6], "big")
                if crc16(data[offset + 2 : offset + 4] + side) != stored:
                    raise ValueError(f"MP3 CRC mismatch at byte {offset}")
                protected += 1
            reservoir = _bits(side, 0, 9 if ver == 3 else 8)
            if reservoir > previous_slots:
                raise ValueError(f"MP3 bit-reservoir underflow at byte {offset}")
            granule_start = (
                9 + (5 if channels == 1 else 3) + 4 * channels
                if ver == 3
                else 8 + (1 if channels == 1 else 2)
            )
            stride = 59 if ver == 3 else 63
            count = channels * (2 if ver == 3 else 1)
            part_bits = 0
            for n in range(count):
                bit = granule_start + n * stride
                part_bits += _bits(side, bit, 12)
                if _bits(side, bit + 12, 9) > 288:
                    raise ValueError(f"invalid MP3 big_values at byte {offset}")
            slots = length - (info_start - offset) - info_length
            if part_bits > (reservoir + slots) * 8:
                raise ValueError(
                    f"MP3 main data exceeds available bits at byte {offset}"
                )
            if not frames:
                positions = {
                    info_start + info_length,
                    offset + 4 + info_length,
                    offset + 36,
                }
                timing_header = any(
                    data[p : p + 4] in {b"Xing", b"Info", b"VBRI"} for p in positions
                )
            previous_slots += slots
            samples += 1152 if ver == 3 else 576
            frames += 1
            if samples / rate > max_seconds + 1:
                raise ValueError("MP3 frame duration exceeds bound")
            offset += length
        if not frames:
            raise ValueError("MP3 contains no complete frames")
        return {
            "frame_count": frames,
            "protected_frames": protected,
            "crc_failures": 0,
            "audio_start_byte": start,
            "audio_end_byte": end,
            "unaccounted_bytes": 0,
            "encoded_samples": samples,
            "sample_rate_hz": rate,
            "channels": channels,
            "frame_duration_seconds": samples / rate,
            "has_timing_header": timing_header,
            "tags": tags,
            "scanner_version": "layer3-contiguous-crc-v1",
        }

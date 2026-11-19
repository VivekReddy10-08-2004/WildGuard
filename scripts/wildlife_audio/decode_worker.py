"""Quiet JSON protocol; native library stderr stays visible to the parent gate."""

import json
import sys

from scripts.wildlife_audio.integrity import _decode_local


def main():
    try:
        result = _decode_local(sys.argv[1], float(sys.argv[2]), int(sys.argv[3]))
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

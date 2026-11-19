"""Bounded subprocess capture; native diagnostics are never inherited unnoticed."""

import subprocess
import threading


def run_bounded(
    command, timeout=120, stdout_limit=2_000_000, stderr_limit=131_072, cwd=None
):
    """Capture small worker responses, not decoded audio. Kill on overflow/timeouts."""
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
    )
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflow = []

    def collect(name, stream, limit):
        while chunk := stream.read(4096):
            remaining = limit - len(buffers[name])
            buffers[name].extend(chunk[: max(0, remaining)])
            if len(chunk) > remaining:
                overflow.append(name)
                process.kill()
                break

    threads = [
        threading.Thread(target=collect, args=("stdout", process.stdout, stdout_limit)),
        threading.Thread(target=collect, args=("stderr", process.stderr, stderr_limit)),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    for thread in threads:
        thread.join()
    process.stdout.close()
    process.stderr.close()
    return {
        "exit_code": process.returncode,
        "stdout": bytes(buffers["stdout"]),
        "stderr": bytes(buffers["stderr"]),
        "timed_out": timed_out,
        "overflow": overflow,
    }

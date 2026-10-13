"""`dungeon-voice` — run the voice service here and share it with other machines.

It starts `tts/run.sh` and opens a reverse SSH tunnel to each host, so that host reaches the service at
http://127.0.0.1:8770 (no firewall rule, nothing listens on the LAN). The tunnel reconnects after a drop.
Stop everything with Ctrl+C.

    uv run dungeon-voice                  # service + tunnel to the Pi
    uv run dungeon-voice --tunnel ""      # service only
    uv run dungeon-voice --engine mock    # test without the GPU model
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time

import httpx

from stage.ttsctl import RUN_SH

DEFAULT_TUNNEL = "pi"  # an ssh host name; DUNGEON_VOICE_TUNNEL overrides it (empty = none)
RETRY_SECONDS = 5


def tunnel_argv(host: str, port: int) -> list[str]:
    return ["ssh", "-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
            "-R", f"127.0.0.1:{port}:127.0.0.1:{port}", host]


def wait_ready(port: int, service: subprocess.Popen, timeout: float = 180.0) -> bool:
    """Poll /health until the model has loaded. False when the service exits or the time runs out."""
    end = time.monotonic() + timeout
    while time.monotonic() < end and service.poll() is None:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def keep_tunnel(host: str, port: int, stop: threading.Event) -> None:
    while not stop.is_set():
        proc = subprocess.Popen(tunnel_argv(host, port), stdin=subprocess.DEVNULL)
        print(f"voice tunnel to {host}: up (the {host} machine reaches the voice at http://127.0.0.1:{port})", flush=True)
        while proc.poll() is None and not stop.wait(1):
            pass
        if proc.poll() is None:
            proc.terminate()
        if not stop.is_set():
            print(f"voice tunnel to {host}: down, retry in {RETRY_SECONDS} s", flush=True)
            stop.wait(RETRY_SECONDS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dungeon-voice", description="Run the voice service and share it over SSH.")
    parser.add_argument("--engine", choices=["f5", "mock"], default="f5")
    parser.add_argument("--port", type=int, default=int(os.environ.get("TTS_PORT", "8770")))
    parser.add_argument("--tunnel", default=os.environ.get("DUNGEON_VOICE_TUNNEL", DEFAULT_TUNNEL),
                        help="ssh host(s), space separated, to share the voice with (default: %(default)s; empty = none)")
    args = parser.parse_args(argv)

    service = subprocess.Popen([str(RUN_SH), args.engine], env={**os.environ, "TTS_PORT": str(args.port)}, start_new_session=True)
    stop = threading.Event()
    threads: list[threading.Thread] = []
    try:
        print(f"voice service: loading the {args.engine} engine (the first start takes a while)…", flush=True)
        if not wait_ready(args.port, service):
            print("voice service: did not start. Read the lines above.", file=sys.stderr)
            return 1
        print(f"voice service: ready at http://127.0.0.1:{args.port}", flush=True)
        for host in args.tunnel.split():
            thread = threading.Thread(target=keep_tunnel, args=(host, args.port, stop), daemon=True)
            thread.start()
            threads.append(thread)
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        while service.poll() is None and not stop.wait(1):
            pass
        return 0 if stop.is_set() else service.returncode or 1
    except KeyboardInterrupt:
        return 0
    finally:
        stop.set()
        for thread in threads:
            thread.join(3)
        if service.poll() is None:
            os.killpg(service.pid, signal.SIGTERM)
            service.wait()


if __name__ == "__main__":
    sys.exit(main())

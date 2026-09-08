#!/usr/bin/env python3
"""Fully detach a command into its own session so it survives parent/process-group
teardown (double-fork + os.setsid). macOS has no `setsid` binary, so we do it here.

Usage: spawn_daemon.py <logfile> <cmd> [args...]
Prints the daemon PID (the grandchild) to stdout.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write("usage: spawn_daemon.py <logfile> <cmd> [args...]\n")
        return 2

    logfile = sys.argv[1]
    cmd = sys.argv[2:]

    # First fork: parent reads the grandchild pid from a pipe, then exits.
    r, w = os.pipe()
    pid = os.fork()
    if pid > 0:
        os.close(w)
        data = os.read(r, 64).decode().strip()
        os.close(r)
        sys.stdout.write(data + "\n")
        sys.stdout.flush()
        return 0

    # Child: become session leader so we detach from the controlling terminal
    # and the launching process group (the agent shell's group).
    os.close(r)
    os.setsid()

    # Second fork: ensure we are not a session leader (can't reacquire a TTY).
    pid2 = os.fork()
    if pid2 > 0:
        os.write(w, str(pid2).encode())
        os.close(w)
        os._exit(0)

    os.close(w)

    # Grandchild: redirect std streams and exec the target command.
    fd_null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(fd_null, 0)
    fd_log = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd_log, 1)
    os.dup2(fd_log, 2)
    try:
        os.execvp(cmd[0], cmd)
    except Exception as e:  # noqa: BLE001
        os.write(2, f"spawn_daemon exec failed: {e}\n".encode())
        os._exit(127)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

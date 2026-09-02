"""Cross-process file locks shared by Booster persistence stores."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def cross_process_file_lock(path: str | Path) -> Iterator[None]:
    """Serializes mutations across independently spawned Booster processes."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
        descriptor = os.open(str(lock_path), flags, 0o666)
    except FileExistsError:
        pass
    else:
        try:
            os.write(descriptor, b"0")
        finally:
            os.close(descriptor)

    stream = None
    for _ in range(200):
        try:
            stream = lock_path.open("r+b")
            break
        except PermissionError:
            time.sleep(0.01)
    if stream is None:
        raise PermissionError(f"Unable to open lock file: {lock_path}")

    with stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            locked = False
            for _ in range(600):
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError as exc:
                    if exc.errno not in (13, 36):
                        raise
                    time.sleep(0.01)
            if not locked:
                raise TimeoutError(f"Unable to acquire lock: {lock_path}")
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

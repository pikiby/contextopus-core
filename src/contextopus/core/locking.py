"""Portable advisory locks accepting either a stream or a file descriptor."""

import os


def _windows_flock(file, operation, *, api=None):
    """Lock the same byte on first acquisition and all later acquisitions."""
    if api is None:
        import msvcrt as api

    fd = file.fileno() if hasattr(file, "fileno") else file
    position = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        # CRT locking supports ranges beyond EOF. Seeding the file is unnecessary
        # and can fail before lock acquisition when another process owns byte 0.
        os.lseek(fd, 0, os.SEEK_SET)
        api.locking(
            fd,
            api.LK_UNLCK
            if operation == LOCK_UN
            else (api.LK_NBLCK if operation & LOCK_NB else api.LK_LOCK),
            1,
        )
    finally:
        os.lseek(fd, position, os.SEEK_SET)


if os.name != "nt":
    from fcntl import flock, LOCK_EX, LOCK_UN, LOCK_NB
else:
    LOCK_EX, LOCK_UN, LOCK_NB = 2, 8, 4
    flock = _windows_flock

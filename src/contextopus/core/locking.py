"""Small portable advisory file-lock adapter (same API as flock)."""

import os

if os.name != "nt":
    from fcntl import flock, LOCK_EX, LOCK_UN, LOCK_NB
else:
    import msvcrt

    LOCK_EX, LOCK_UN, LOCK_NB = 2, 8, 4

    def flock(fd, operation):
        position = os.lseek(fd, 0, os.SEEK_CUR)
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            msvcrt.locking(
                fd,
                msvcrt.LK_UNLCK
                if operation == LOCK_UN
                else (msvcrt.LK_NBLCK if operation & LOCK_NB else msvcrt.LK_LOCK),
                1,
            )
        finally:
            os.lseek(fd, position, os.SEEK_SET)

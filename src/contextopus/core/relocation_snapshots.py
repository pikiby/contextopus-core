"""Snapshot coordinates and opaque archive recognition for root relocation."""

from pathlib import PurePosixPath


def archive_path(relative):
    """Historical raw files are byte archives, even when they look like SQLite."""
    parts = PurePosixPath(relative).parts
    return (parts[:2] == (".backups", "relocations")
            or parts[:3] == ("core", "relocation", "raw"))


def snapshot_target(relative, snapshot_id=None):
    """Missing identity means the coordinates of an already reviewed v1 plan."""
    prefix = (PurePosixPath(".backups/relocations", snapshot_id)
              if snapshot_id is not None else PurePosixPath("core/relocation/raw"))
    return str(prefix / relative)


def validate_snapshot_id(proposal):
    if proposal.get("version") == 1:
        if "snapshot_id" in proposal:
            raise ValueError("Version 1 relocation cannot declare a snapshot identity")
        return
    identity = proposal.get("snapshot_id")
    if (not isinstance(identity, str) or len(identity) != 64
            or any(character not in "0123456789abcdef" for character in identity)):
        raise ValueError("Invalid relocation snapshot identity")

"""Prepare shared PBX storage and check it with the worker's real permissions."""

import json
import os
from pathlib import Path
import tempfile
import time


class ProvisioningStorageError(RuntimeError):
    pass


def _open_directory(path):
    if not path:
        raise ValueError("Missing directory")
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def prepare_pbx_storage(config_dir, sounds_dir):
    """Run in private web, before the capability-restricted UID 0 worker starts.

    Touch only the two shared mount roots and the generated speech directory.
    Existing files, Asterisk's runtime state, and provisioning secrets are untouched.
    Asterisk must mount these generated resources read-only.
    """
    for label, path in (("PBX configuration", config_dir), ("PBX sounds", sounds_dir)):
        try:
            fd = _open_directory(path)
            try:
                os.fchown(fd, 0, 0)
                os.fchmod(fd, 0o755)
                if label == "PBX sounds":
                    try:
                        os.mkdir("tts", mode=0o755, dir_fd=fd)
                    except FileExistsError:
                        pass
                    child = os.open("tts", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        os.fchown(child, 0, 0)
                        os.fchmod(child, 0o755)
                    finally:
                        os.close(child)
            finally:
                os.close(fd)
        except (OSError, ValueError):
            raise ProvisioningStorageError(f"Cannot prepare {label} storage for phone provisioning.") from None


def check_worker_storage(profile_dir, receipt_dir, config_dir, sounds_dir):
    """Probe create/replace/delete, not just mode bits or container liveness."""
    for label, path in (
        ("phone profiles", profile_dir),
        ("PBX configuration", config_dir),
        ("PBX speech", str(Path(sounds_dir) / "tts") if sounds_dir else ""),
    ):
        try:
            fd = _open_directory(path)
            os.close(fd)
            # A unique, empty probe never replaces generated config or profiles.
            with tempfile.TemporaryDirectory(prefix=".frontporch-storage-", dir=path) as probe:
                source, destination = Path(probe) / "new", Path(probe) / "current"
                source.write_bytes(b"storage check")
                destination.write_bytes(b"old")
                source.replace(destination)
                if destination.read_bytes() != b"storage check":
                    raise OSError("Probe did not round-trip")
        except (OSError, ValueError):
            raise ProvisioningStorageError(f"Phone provisioner cannot write {label} storage.") from None
    try:
        fd = _open_directory(receipt_dir)
        try:
            os.listdir(fd)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        raise ProvisioningStorageError("Phone provisioner cannot read phone receipts.") from None


def check_worker_health(environ=os.environ, clock=time.time):
    check_worker_storage(
        environ.get("PHONE_PROFILE_DIR", ""), environ.get("PHONE_RECEIPT_DIR", ""),
        environ.get("ASTERISK_GENERATED_CONFIG_DIR", ""), environ.get("ASTERISK_CUSTOM_SOUNDS_DIR", ""),
    )
    try:
        heartbeat = Path(environ["PHONE_PROFILE_DIR"]) / "worker-health.json"
        at = json.loads(heartbeat.read_text())["at"]
        if type(at) not in (int, float) or not 0 <= clock() - at < 600:
            raise ValueError("Stale heartbeat")
    except (OSError, ValueError, TypeError, KeyError):
        raise ProvisioningStorageError("Phone provisioner heartbeat is missing or stale.") from None


if __name__ == "__main__":
    try:
        check_worker_health()
    except ProvisioningStorageError as error:
        raise SystemExit(str(error)) from None

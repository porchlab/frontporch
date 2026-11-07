"""Smoke-test the built Django image with disposable PostgreSQL and fictional data."""

import os
import subprocess
import sys
import time
import uuid


def inside(mode):
    import django
    django.setup()
    from django.core.management import call_command
    from django.test import Client

    call_command("check")
    if mode.startswith("storage-"):
        import json
        from pathlib import Path
        from frontporch.provisioning_storage import check_worker_health, ProvisioningStorageError
        config, sounds, profiles, receipts = map(Path, ("/storage/config", "/storage/sounds", "/storage/profiles", "/storage/receipts"))
        if mode == "storage-seed":
            (sounds / "tts").mkdir(exist_ok=True)
            for path in (config, sounds, sounds / "tts"):
                os.chown(path, 1000, 1000)
                path.chmod(0o755)
            for path in (profiles, receipts):
                path.chmod(0o700)
            (config / "existing.conf").write_text("; preserve existing generated files\n")
            (profiles / "worker-health.json").write_text(json.dumps({"at": time.time()}))
        elif mode == "storage-prepare":
            call_command("prepare_phone_provisioning_storage")
        elif mode == "storage-denied":
            try:
                check_worker_health()
            except ProvisioningStorageError as error:
                assert "PBX configuration" in str(error)
            else:
                raise AssertionError("Unwritable PBX storage passed health with a fresh heartbeat")
        elif mode == "storage-ready":
            from directory.asterisk.renderer import _atomic_write
            check_worker_health()
            assert config.stat().st_uid == 0
            assert (sounds / "tts").stat().st_uid == 0
            assert (config / "existing.conf").read_text() == "; preserve existing generated files\n"
            probe = config / "storage-test.conf"
            _atomic_write(probe, "; first\n")
            _atomic_write(probe, "; replaced\n")
            assert probe.read_text() == "; replaced\n"
            probe.unlink()
        else:
            raise ValueError("Unknown storage test")
        return
    if mode == "speech":
        from directory.asterisk.tts import TextToSpeechPromptGenerator, spoken_prompt, text_to_speech_settings
        result = TextToSpeechPromptGenerator(custom_sounds_dir="/tmp/smoke-prompts").generate(
            [spoken_prompt("Welcome to FrontPorch.", text_to_speech_settings())],
        )
        assert len(result.generated_files) == 1
        assert result.generated_files[0].stat().st_size > 0
        return
    if mode == "private":
        call_command("migrate", interactive=False, verbosity=0)
    call_command("collectstatic", interactive=False, verbosity=0)
    client = Client(HTTP_HOST="parents.example.com")
    assert client.get("/welcome/", secure=True).status_code == 200
    assert client.get("/accounts/login/", secure=True).status_code == 200
    assert client.get("/children/", secure=True).status_code == 302
    assert client.get("/admin/", secure=True).status_code == (404 if mode == "public" else 302)
    # Exercise the actual server and packaged application import, too.
    subprocess.run(["gunicorn", "--check-config", "frontporch.wsgi:application"], check=True)


def smoke(image):
    name = "frontporch-image-test-" + uuid.uuid4().hex[:10]

    def docker(*args, **kwargs):
        return subprocess.run(["docker", *args], check=True, **kwargs)

    # Named volumes preserve real Linux ownership even on Docker Desktop.
    volumes = []
    try:
        for directory in ("config", "sounds", "profiles", "receipts"):
            volume = name + "-" + directory
            docker("volume", "create", volume)
            volumes.append((volume, directory))
        for mode in ("seed", "denied", "prepare", "ready", "readonly"):
            mounts = []
            for volume, directory in volumes:
                readonly = ":ro" if (directory == "receipts" and mode != "seed") or (mode == "readonly" and directory == "config") else ""
                mounts += ["-v", f"{volume}:/storage/{directory}{readonly}"]
            restricted = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "0:0"] if mode in ("denied", "ready", "readonly") else []
            docker("run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp", *restricted, *mounts,
                   "-e", "DJANGO_SETTINGS_MODULE=frontporch.settings", "-e", "PHONE_ENROLLMENT_ENABLED=true",
                   "-e", "DATABASE_URL=postgresql://storage-test:storage-test@127.0.0.1/storage-test",
                   "-e", "ASTERISK_AUTO_APPLY_CONFIG=false",
                   "-e", "ASTERISK_GENERATED_CONFIG_DIR=/storage/config", "-e", "ASTERISK_CUSTOM_SOUNDS_DIR=/storage/sounds",
                   "-e", "PHONE_PROFILE_DIR=/storage/profiles", "-e", "PHONE_RECEIPT_DIR=/storage/receipts",
                   image, "python", "deploy/test_release_image.py", "--inside", "storage-" + ("denied" if mode == "readonly" else mode))
    finally:
        for volume, _ in reversed(volumes):
            docker("volume", "rm", volume)
    docker("network", "create", "--internal", name)
    try:
        docker("run", "-d", "--name", name, "--network", name, "--network-alias", "db",
               "-e", "POSTGRES_PASSWORD=image-test-only", "-e", "POSTGRES_DB=frontporch", "postgres:16")
        for _ in range(60):
            result = subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Disposable PostgreSQL did not start")
        for mode in ("private", "public", "speech"):
            docker("run", "--rm", "--network", "none" if mode == "speech" else name,
                   "-e", "DATABASE_URL=postgres://postgres:image-test-only@db:5432/frontporch",
                   "-e", "DJANGO_SECRET_KEY=" + "image-test-only-" * 5,
                   "-e", "DJANGO_ALLOWED_HOSTS=parents.example.com",
                   "-e", "FRONTPORCH_PUBLIC_HOST=parents.example.com",
                   "-e", "ASTERISK_AUTO_APPLY_CONFIG=false",
                   "-e", "DJANGO_SETTINGS_MODULE=frontporch." + ("public_settings" if mode == "public" else "settings"),
                   image, "python", "deploy/test_release_image.py", "--inside", mode)
    finally:
        subprocess.run(["docker", "rm", "-fv", name], check=False)
        docker("network", "rm", name)


if __name__ == "__main__":
    if sys.argv[1] == "--inside":
        # Executing a file inside deploy/ places deploy/, not /app, on sys.path.
        sys.path.insert(0, os.getcwd())
        inside(sys.argv[2])
    else:
        smoke(sys.argv[1])

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

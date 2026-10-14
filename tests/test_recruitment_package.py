"""Delivery guards and a real Git snapshot with ignored local configuration."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "package_recruitment", Path(__file__).resolve().parents[1] / "scripts/package_recruitment.py"
)
assert spec is not None and spec.loader is not None
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


@pytest.mark.parametrize("name", [
    ".env", "frontend/.env.local", ".env-production", ".git/config", "../outside.txt",
    "frontend/node_modules/package/index.js", "data/city.db", "artifacts/browser/state.json",
])
def test_rejects_local_state_and_sensitive_source_paths(name):
    with pytest.raises(ValueError):
        delivery.check_source_path(name)


def test_keeps_redacted_configuration_examples():
    delivery.check_source_path(".env.example")
    delivery.check_source_path("frontend/.env.example")
    delivery.check_content(".env.example", b"DEEPSEEK_API_KEY=your-deepseek-api-key")


def test_credential_rejection_does_not_repeat_value():
    token = b"ghp_" + b"a" * 40
    with pytest.raises(ValueError) as caught:
        delivery.check_content("config.py", token)
    assert "config.py" in str(caught.value)
    assert token.decode() not in str(caught.value)


@pytest.mark.skipif(shutil.which("git") is None, reason="Delivery export requires Git")
def test_package_matches_commit_and_excludes_ignored_environment(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {name: b"test material\n" for name in delivery.REQUIRED}
    files.update({
        "docs/recruitment/package-index.html": b"Source @@SOURCE_COMMIT@@",
        "docs/recruitment/verification.md": b"Validated test snapshot",
        ".gitignore": b".env\n",
        "src/sample.py": b"print('hello')\n",
    })
    for name, data in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (repo / ".env").write_bytes(b"LOCAL_PRIVATE_VALUE=must-stay-local\n")
    for args in [
        ["init", "-b", "test-delivery"], ["add", "."],
        ["-c", "user.name=Delivery Test", "-c", "user.email=test@example.invalid", "commit", "-m", "Test snapshot"],
    ]:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    monkeypatch.setattr(delivery, "ROOT", repo)
    result = delivery.package(tmp_path / "output")
    commit = delivery.git("rev-parse", "HEAD").decode().strip()
    with zipfile.ZipFile(result) as archive:
        prefix = result.stem + "/"
        names = archive.namelist()
        assert not any(name.endswith("/.env") or "/.git/" in name for name in names)
        assert archive.read(prefix + "04-source/CityClean-Agent/src/sample.py") == delivery.git("show", f"{commit}:src/sample.py")
        assert commit.encode() in archive.read(prefix + "00-start-here.html")
        manifest = json.loads(archive.read(prefix + "manifest.json"))
        assert manifest["source_commit"] == commit
        assert manifest["source_file_count"] == len(files)
        for entry in manifest["files"]:
            assert hashlib.sha256(archive.read(prefix + entry["path"])).hexdigest() == entry["sha256"]
    with pytest.raises(FileExistsError):
        delivery.package(tmp_path / "output")
    (repo / "src/sample.py").write_text("uncommitted change", encoding="utf-8")
    with pytest.raises(RuntimeError, match="source changes"):
        delivery.package(tmp_path / "another-output")

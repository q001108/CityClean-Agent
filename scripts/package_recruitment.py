"""Package a clean committed source snapshot and offline recruitment materials."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "docs/recruitment/project-overview.pdf": "01-project-overview.pdf",
    "docs/recruitment/getting-started.pdf": "02-getting-started.pdf",
    "docs/media/cityclean-demo.mp4": "03-demo.mp4",
}
BLOCKED_PARTS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv", ".playwright-cli"}
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}"),
    re.compile(rb"\bsk-[A-Za-z0-9]{24,}"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
)


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def check_source_path(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or any(part in BLOCKED_PARTS for part in path.parts):
        raise ValueError(f"Unexpected source path: {name}")
    if (path.name == ".env" or path.name.startswith((".env.", ".env-"))) and path.name != ".env.example":
        raise ValueError(f"Local environment file must not be packaged: {name}")
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".pyc", ".pem", ".key"}:
        raise ValueError(f"Runtime or sensitive file must not be packaged: {name}")
    if len(path.parts) > 1 and path.parts[0] == "artifacts" and name != "artifacts/README.md":
        raise ValueError(f"Generated artifact must not be packaged: {name}")
    if len(path.parts) > 1 and path.parts[:2] == ("frontend", "dist"):
        raise ValueError(f"Generated frontend build must not be packaged: {name}")


def check_content(name: str, data: bytes) -> None:
    if b"\0" not in data[:4096] and any(pattern.search(data) for pattern in SECRET_PATTERNS):
        raise ValueError(f"Possible credential in {name}; value withheld")


def package(output_dir: Path) -> Path:
    if git("status", "--porcelain").strip():
        raise RuntimeError("Commit or review all source changes before packaging; no dirty snapshot is allowed.")
    commit = git("rev-parse", "HEAD").decode().strip()
    branch = git("branch", "--show-current").decode().strip()
    source_archive = zipfile.ZipFile(io.BytesIO(git("-c", "core.autocrlf=false", "archive", "--format=zip", "HEAD")))
    source_files = {
        name: source_archive.read(name)
        for name in source_archive.namelist()
        if not name.endswith("/")
    }
    for name, data in source_files.items():
        check_source_path(name)
        check_content(name, data)
    for name in (*REQUIRED, "docs/recruitment/package-index.html", "docs/recruitment/verification.md"):
        if name not in source_files:
            raise RuntimeError(f"Missing committed recruitment material: {name}")

    date = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    name = f"CityClean-Agent_刘东海_校招投递_{date}_{commit[:8]}"
    output_dir = output_dir.resolve()
    bundle = output_dir / name
    archive_path = output_dir / f"{name}.zip"
    if bundle.exists() or archive_path.exists():
        raise FileExistsError(f"Refusing to overwrite an existing delivery: {name}")
    bundle.mkdir(parents=True)
    source_prefix = "04-source/CityClean-Agent/"
    payload = {source_prefix + name: data for name, data in source_files.items()}
    payload.update({destination: source_files[origin] for origin, destination in REQUIRED.items()})
    payload["00-start-here.html"] = source_files["docs/recruitment/package-index.html"].replace(
        b"@@SOURCE_COMMIT@@", commit.encode()
    )
    payload["README.txt"] = (
        "CityClean-Agent | 刘东海 | 校招项目投递包\n\n"
        "解压后双击 00-start-here.html，查看项目资料并播放演示视频。\n"
        "01-project-overview.pdf：整体项目说明、架构、评测与边界。\n"
        "02-getting-started.pdf：Docker / 本地开发启动说明及演示步骤。\n"
        "03-demo.mp4：约 73 秒实际工作台录制，无声，H.264。\n"
        "04-source/CityClean-Agent/：完整已提交源码，含前后端、测试和评测资源。\n\n"
        "阅读和播放可以离线；首次安装运行依赖需要联网。默认演示无需 API Key 或 GPU。\n"
        "城市运营数据为合成数据；实时模型调用需要单独配置。\n"
        "GitHub 仓库在整理时为私有，招聘方可直接使用此包。\n"
        f"源码提交：{commit}\n分支：{branch}\n"
        "文件摘要见 manifest.json 与 SHA256SUMS.txt。\n"
    ).encode("utf-8")
    entries = [
        {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(payload.items())
    ]
    manifest = {
        "project": "CityClean-Agent",
        "author": "刘东海",
        "package_date": date,
        "source_commit": commit,
        "source_branch": branch,
        "repository": "https://github.com/q001108/CityClean-Agent",
        "repository_visibility_at_preparation": "private",
        "source_file_count": len(source_files),
        "source_archive": "git archive HEAD",
        "excluded": ["Git history", "untracked and ignored files", "local secrets", "caches", "node_modules", "runtime databases"],
        "verification_record": source_prefix + "docs/recruitment/verification.md",
        "files": entries,
    }
    payload["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    payload["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(payload.items())
    ).encode("utf-8")
    for name, data in payload.items():
        path = bundle.joinpath(*PurePosixPath(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(payload):
            archive.write(bundle.joinpath(*PurePosixPath(name).parts), f"{bundle.name}/{name}")
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity verification failed")
        for name, data in payload.items():
            if archive.read(f"{bundle.name}/{name}") != data:
                raise RuntimeError(f"ZIP content mismatch: {name}")
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive_path.name}\n", encoding="utf-8")
    print(json.dumps({"zip": str(archive_path), "folder": str(bundle), "source_commit": commit,
                      "source_file_count": len(source_files), "zip_bytes": archive_path.stat().st_size,
                      "sha256": checksum}, ensure_ascii=False, indent=2))
    return archive_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/recruitment")
    args = parser.parse_args()
    package(args.output_dir)

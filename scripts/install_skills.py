from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from release_tools import manifest_paths


NAMES = ("paper-workflow", "paper-search", "paper-fulltext-fetcher", "paper-corpus")


def runtime_files(root):
    return manifest_paths(root, "runtime")


def install(root, destination, execute=False):
    destination = destination.expanduser().resolve()
    if destination == (root / ".agents/skills").resolve():
        raise ValueError("Repository skills are already present; do not install over source files")
    sources = runtime_files(root)
    hashes = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    version = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]
    runtime_relative = Path(".paper-fulltext-runtime") / version
    conflicts = [name for name in NAMES if (destination / name).exists()]
    plan = {"mode": "execute" if execute else "dry_run", "skills": list(NAMES), "runtime": runtime_relative.as_posix(), "conflicts": conflicts, "copies_virtual_environment": False, "changes_network_settings": False}
    if conflicts:
        raise ValueError("Existing skill folders must be reviewed first: " + ", ".join(conflicts))
    for name in NAMES:
        if not (root / ".agents/skills" / name / "SKILL.md").is_file():
            raise ValueError("Incomplete skill source bundle")
    if not execute:
        return plan
    runtime = destination / runtime_relative
    if runtime.exists():
        if any(not (runtime / relative).is_file() or hashlib.sha256((runtime / relative).read_bytes()).hexdigest() != expected for relative, expected in hashes.items()):
            raise ValueError("Existing shared runtime does not match the source bundle")
    else:
        runtime.mkdir(parents=True, exist_ok=False)
        for source in sources:
            target = runtime / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as reader, target.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
            if hashlib.sha256(target.read_bytes()).hexdigest() != hashes[source.relative_to(root).as_posix()]:
                raise ValueError("Source changed during installation")
        with (runtime / "bundle-manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(hashes, stream, indent=2)
    for name in NAMES:
        source = root / ".agents/skills" / name
        target = destination / name
        target.mkdir(parents=True, exist_ok=False)
        content = (source / "SKILL.md").read_text(encoding="utf-8").replace("../../../", "../" + runtime_relative.as_posix() + "/")
        with (target / "SKILL.md").open("x", encoding="utf-8") as stream:
            stream.write(content)
        (target / "agents").mkdir()
        shutil.copyfile(source / "agents/openai.yaml", target / "agents/openai.yaml")
    plan["next"] = "Run scripts/bootstrap.ps1 in the shared runtime on Windows, or create its .venv and install requirements.txt on Linux/macOS; install Corpus dependencies only when needed."
    return plan


def main():
    parser = argparse.ArgumentParser(description="Install four skills and one versioned shared runtime; preview by default")
    parser.add_argument("--destination", type=Path, default=Path.home() / ".agents/skills")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(install(Path(__file__).resolve().parents[1], args.destination, args.execute), ensure_ascii=False, indent=2))
        return 0
    except ValueError as error:
        print(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

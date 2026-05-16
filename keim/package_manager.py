from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import shutil
import zipfile


@dataclass(slots=True)
class PackageInfo:
    name: str
    version: str
    path: str
    permissions: tuple[str, ...] = ()


class KeimPackageManager:
    """Minimaler lokaler Paketmanager: keim get/install/list.

    Kein zentraler Store, keine Cloud-Pflicht. Pakete sind Ordner oder ZIPs mit
    optionaler keim_package.json. v5 speichert zusätzlich deklarierte
    Berechtigungen aus dem Paketmanifest.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or Path.cwd())
        self.pkg_dir = self.root / ".keim_packages"
        self.pkg_dir.mkdir(exist_ok=True)
        self.lockfile = self.root / "keim.lock.json"

    def init_manifest(self, name: str) -> Path:
        manifest = self.root / "keim.json"
        if not manifest.exists():
            manifest.write_text(json.dumps({"name": name, "version": "0.1.0", "dependencies": {}, "permissions": []}, indent=2), encoding="utf-8")
        return manifest

    def install(self, source: str, name: str | None = None) -> PackageInfo:
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(source)
        if src.is_file() and src.suffix.lower() == ".zip":
            with zipfile.ZipFile(src) as z:
                meta = self._read_zip_meta(z)
                pkg_name = name or meta.get("name") or src.stem
                dest = self.pkg_dir / str(pkg_name)
                if dest.exists():
                    shutil.rmtree(dest)
                dest.mkdir(parents=True)
                z.extractall(dest)
        elif src.is_dir():
            meta_path = src / "keim_package.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            pkg_name = name or meta.get("name") or src.name
            dest = self.pkg_dir / str(pkg_name)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            raise ValueError("Paketquelle muss Ordner oder ZIP sein.")
        version = str(meta.get("version", "0.0.0"))
        permissions = tuple(str(x) for x in meta.get("permissions", []))
        self._record(str(pkg_name), version, str(dest), permissions)
        return PackageInfo(str(pkg_name), version, str(dest), permissions)

    def list(self) -> list[PackageInfo]:
        if not self.lockfile.exists():
            return []
        data = json.loads(self.lockfile.read_text(encoding="utf-8"))
        return [
            PackageInfo(k, v.get("version", "0.0.0"), v.get("path", ""), tuple(v.get("permissions", [])))
            for k, v in sorted(data.get("packages", {}).items())
        ]

    def _record(self, name: str, version: str, path: str, permissions: tuple[str, ...] = ()) -> None:
        data = {"packages": {}}
        if self.lockfile.exists():
            data = json.loads(self.lockfile.read_text(encoding="utf-8"))
        data.setdefault("packages", {})[name] = {"version": version, "path": path, "permissions": list(permissions)}
        self.lockfile.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _read_zip_meta(self, z: zipfile.ZipFile) -> dict[str, object]:  # type: ignore[name-defined]
        for n in z.namelist():
            if n.endswith("keim_package.json"):
                return json.loads(z.read(n).decode("utf-8"))
        return {}

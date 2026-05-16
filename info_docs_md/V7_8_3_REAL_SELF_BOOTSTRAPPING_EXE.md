# Keim v7.8.3 – Real Self-Bootstrapping EXE Launcher

v7.8.3 macht den Full-EXE-Launcher praktisch nutzbar: `bin/<name>_launcher.exe` ist kein Hinweistext mehr. Er startet die Runtime-Bundle-Datei `run.bat` und wartet auf deren Ende.

## Technischer Kern

Windows PE64:

```text
Keim internal linker
→ PE32+ x86_64
→ importiert msvcrt.dll!system
→ ruft cmd.exe /d /c call "<package>\run.bat"
→ wartet auf Abschluss
```

Linux ELF64:

```text
Keim internal linker
→ ELF64 x86_64
→ execve("/bin/sh", ["sh", "-c", "<package>/run.sh"], NULL)
```

## Verifikation

`exe-verify` prüft:

- MZ/ELF-Header
- echter Runtime-Launcher
- kein Hinweis-Stub
- `msvcrt.dll`/`system`/`run.bat` bei PE
- `/bin/sh`/`run.sh` bei ELF

## Nutzung

```powershell
python -m keim exe-pack src/main.keim --out build/app --name app
build/app/bin/app_launcher.exe
```

Für GPU-Pakete:

```powershell
python -m keim exe-pack src/main.keim --out build/app --name app --gpu-driver driver/build/CC_OpenCl.dll
build/app/bin/app_launcher.exe
```

Der Launcher setzt nicht selbst die GPU-Umgebung. Das erledigt `run.bat`/`run.sh`, die vom Launcher gestartet werden.

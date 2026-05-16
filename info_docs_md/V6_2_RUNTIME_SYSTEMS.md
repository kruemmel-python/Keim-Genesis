# Keim Genesis v6.2 Runtime Systems

v6.2 ergänzt den v6.1 Compiler-Core um erste Runtime-Systeme:

- `kanal<T>`, `sende`, `empfange`
- minimales `akteur` / `bei` / `starte` / `frage` Modell
- Snapshot-Dateien mit `keim-snapshot-v1`
- Replay-Eventlog mit `keim-replay-v1`
- `core-run --record`
- `core-replay`

## Beispiel

```keim
speicher ch ist kanal<ganzzahl> setzt kanal()
sende ch 42
speicher wert ist ganzzahl setzt empfange(ch)
```

Actors sind in dieser Version single-threaded. Mailbox-Scheduling, Backpressure und Deadlock-Diagnose bleiben Folgearbeiten.

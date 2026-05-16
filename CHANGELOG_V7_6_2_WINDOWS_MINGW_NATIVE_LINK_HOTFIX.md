# Changelog v7.6.2 Windows MinGW Native Link Hotfix

- Der v6.5 Native-MVP-Generator wurde weiter gehärtet:
  - kein `std::vector` mehr im generierten keimvm65-Subset
  - feste C-ähnliche Stack-/Slot-Arrays
  - dadurch weniger Abhängigkeit von libstdc++-Linking und MinGW-Runtime-Pfaden
- Der v6.5 Native-Test kompiliert mit Retry-Strategie:
  - `-O2`
  - `-O0`
  - unter Windows optional statische libstdc++/libgcc
  - Fallback auf kurzen temporären Pfad
- Der Test erweitert bei Fehlern die Diagnose um vollständige stdout/stderr-Logs aller Compile-Versuche.

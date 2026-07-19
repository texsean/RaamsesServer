# RGS Windows

Windows build of the **RGS** (Raamses Gateway Server).

## Project Structure

- `src/linux/` — Linux C++ / Python implementation
- `src/windows/` — Windows C++ implementation (this folder)
- `src/android/` — Android console app (Kotlin/Jetpack Compose)

## Building

TODO: Add Windows build instructions once C++23 implementation is ported.

The Windows build targets:
- Visual Studio 2022 / MSVC
- C++23
- Windows Subsystem for Linux (WSL) alternative path

## Notes

The protocol, message types, and gateway routing are shared across platforms.
Only the network I/O and platform-specific code differ.

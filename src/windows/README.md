# RGS Windows

Windows build of the **RGS (Raamses Gateway Server)**.

## Prerequisites

- Visual Studio 2022 (or newer) with C++23 support
- CMake 3.26+
- Windows SDK

## Building

```bash
cd src/windows
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

## Architecture

The Windows build shares core logic with the Linux build:
- **core/** — ConfigLoader (INI-style config parsing)
- **logging/** — Thread-safe logger with timestamped output
- **verifier/** — Agent task verification engine

Platform-specific code:
- Networking (Winsock on Windows, POSIX sockets on Linux)
- Threading (std::thread is cross-platform)
- File I/O (std::fstream is cross-platform)

## Config

Place `rgs.config` in the working directory:

```
port=8765
heartbeat=30
log_level=info
```

## Notes

- The C++ code targets C++23 and uses `#ifdef _WIN32` for platform-specific sections
- The Python gateway (port 8765) and Android console (port 42000, JSON protocol) are separate
- This Windows build will provide the same gateway functionality as the Linux version

# Raamses Gateway Server (RGS) - Windows Version

**Location**: `src/windows/rgs/`
**Platform**: .NET 8 WPF / WinUI (XAML)
**Purpose**: Windows desktop operations console for RAAMSES with 3-section layout.

## 3-Section Layout (as requested)

### Left Panel
- Server configuration options (modifiable on-the-fly)
- Apply button
- Default verification mode: **Blink**
- Logfile list at bottom (current debug log selected by default)

### Right Panel
- **Top**: Row of icons (XAML) showing connected displays
- **Middle**: Raw communication (to/from displays + to/from agents)
- **Bottom third**: Tailing current log
  - Format: `mmddyy-hhmmss.nnn` TAB `MethodName` TAB `Detail string`

## AgentType Support
- Enum: Hermes, Claude, Default
- Server detects all agents on startup
- Reports `<agentcount>` and `<agentType>` elements

## Build & Run
dotnet build
dotnet run

## Git Discipline
Always: `git pull --rebase` then `git push` (multi-developer repo)
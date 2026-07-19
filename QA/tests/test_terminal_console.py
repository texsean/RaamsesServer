from src.python.raamses.console.terminal_console import HtopTerminalConsole


def test_console_initializes():
    console = HtopTerminalConsole(mode="full")
    assert console.mode == "full"
    assert console.connected is False

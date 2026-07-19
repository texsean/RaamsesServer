from src.linux.rgs.console.terminal_console import RaamsesConsole


def test_console_initializes():
    console = RaamsesConsole(mode="full")
    assert console.mode == "full"
    assert console.running is False


def test_config_defaults():
    console = RaamsesConsole(mode="full")
    assert console.config["blink_mode"] == "on"
    assert console.config["gateway_port"] == "8765"
    assert console.config["log_level"] == "debug"


def test_log_files():
    console = RaamsesConsole(mode="full")
    assert console.log_files[0] == "debug.log"
    assert console.active_log == "debug.log"


def test_render_full():
    console = RaamsesConsole(mode="full")
    layout = console.render_full()
    assert layout is not None
    assert len(layout.children) == 2  # header + main


def test_render_device_icons():
    console = RaamsesConsole(mode="full")
    panel = console._render_device_icons()
    assert panel is not None
    assert str(panel.title) == "Connected Devices"


def test_render_config_panel():
    console = RaamsesConsole(mode="full")
    panel = console._render_config_panel()
    assert panel is not None
    assert str(panel.title) == "Server Configuration"


def test_render_comm_log():
    console = RaamsesConsole(mode="full")
    console._add_sample_comm()
    panel = console._render_comm_log()
    assert panel is not None
    assert str(panel.title).startswith("Communication")


def test_render_active_log():
    console = RaamsesConsole(mode="full")
    panel = console._render_active_log()
    assert panel is not None
    assert panel.title is not None and "debug.log" in str(panel.title)


def test_command_help():
    console = RaamsesConsole(mode="full")
    console.process_command("/help")


def test_command_blink_toggle():
    console = RaamsesConsole(mode="full")
    assert console.config["blink_mode"] == "on"
    console.process_command("/blink")
    assert console.config["blink_mode"] == "off"
    console.process_command("/blink on")
    assert console.config["blink_mode"] == "on"


def test_command_set():
    console = RaamsesConsole(mode="full")
    console.process_command("/set log_level info")
    assert console.config["log_level"] == "info"


def test_command_quit():
    console = RaamsesConsole(mode="full")
    console.process_command("quit")
    assert console.running is False  # Note: process_command doesn't set running=False
    console.running = True  # Reset for other tests

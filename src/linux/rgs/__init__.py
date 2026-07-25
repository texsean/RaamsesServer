"""RGS — Raamses Gateway Server protocol library.

Provides message types, the gateway server, device clients, and console tools
for the Raamses multi-device agent network.
"""

__all__ = [
    # Message types
    "RaamsesMessage",
    "Header",
    "Register",
    "RegisterAck",
    "Command",
    "CommandResult",
    "Heartbeat",
    "Alert",
    "AgentUpdate",
    "TokenUsage",
    "Capabilities",
    # Server
    "GatewayServer",
    "MessageRouter",
    "SessionRegistry",
    "AgentSession",
    # Clients
    "DeviceClient",
    "DeviceEmulator",
    # Console
    "RADARConsole",
    "ServerAwareConsole",
    # Trust but Verify + Report Issue
    "TrustVerifier",
    "report_issue",
    "SiteConfig",
    "get_site_id",
]


def __getattr__(name: str):
    """Lazy import to avoid pulling in optional dependencies at package level."""
    _lazy_map = {
        "RaamsesMessage": ("rgs.messages.envelope", "RaamsesMessage"),
        "Header": ("rgs.messages.envelope", "Header"),
        "Register": ("rgs.messages.register", "Register"),
        "RegisterAck": ("rgs.messages.register", "RegisterAck"),
        "Command": ("rgs.messages.command", "Command"),
        "CommandResult": ("rgs.messages.command", "CommandResult"),
        "Heartbeat": ("rgs.messages.heartbeat", "Heartbeat"),
        "Alert": ("rgs.messages.alert", "Alert"),
        "AgentUpdate": ("rgs.messages.agent_update", "AgentUpdate"),
        "TokenUsage": ("rgs.messages.agent_update", "TokenUsage"),
        "Capabilities": ("rgs.messages.register", "Capabilities"),
        "GatewayServer": ("rgs.server.gateway", "GatewayServer"),
        "MessageRouter": ("rgs.server.message_router", "MessageRouter"),
        "SessionRegistry": ("rgs.server.session_registry", "SessionRegistry"),
        "AgentSession": ("rgs.server.session_registry", "AgentSession"),
        "DeviceClient": ("rgs.client.device_client", "DeviceClient"),
        "DeviceEmulator": ("rgs.client.device_emulator", "DeviceEmulator"),
        "RADARConsole": ("rgs.console.radar", "RADARConsole"),
        "ServerAwareConsole": ("rgs.console.server_console", "ServerAwareConsole"),
        "TrustVerifier": ("rgs.verifier", "TrustVerifier"),
        "report_issue": ("rgs.report_issue", "report_issue"),
        "SiteConfig": ("rgs.site_config", "SiteConfig"),
        "get_site_id": ("rgs.site_config", "get_site_id"),
    }
    if name in _lazy_map:
        module_path, attr_name = _lazy_map[name]
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

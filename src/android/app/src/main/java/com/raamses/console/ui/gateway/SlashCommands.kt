package com.raamses.console.ui.gateway

import com.raamses.console.ui.theme.*

/**
 * All available slash commands dispatched through the RAAMSES gateway.
 * Each command goes to the server, which routes to the target agent,
 * and the response comes back to this console.
 */
enum class SlashCommand(
    val command: String,
    val description: String,
    val usage: String,
    val category: CommandCategory,
    val takesArg: Boolean = true
) {
    // ── Agent Control ──
    AGENTS("/agents", "List all agents and their status", "/agents", CommandCategory.AGENTS, false),
    AGENT("/agent", "Focus on a specific agent", "/agent <id>", CommandCategory.AGENTS),
    APPROVE("/approve", "Approve a pending agent action", "/approve <agent_id>", CommandCategory.AGENTS),
    REJECT("/reject", "Reject a pending agent action", "/reject <agent_id>", CommandCategory.AGENTS),
    PAUSE("/pause", "Pause an agent", "/pause <agent_id>", CommandCategory.AGENTS),
    RESUME("/resume", "Resume a paused agent", "/resume <agent_id>", CommandCategory.AGENTS),
    STOP("/stop", "Stop an agent", "/stop <agent_id>", CommandCategory.AGENTS),
    RESTART("/restart", "Restart an agent", "/restart <agent_id>", CommandCategory.AGENTS),

    // ── Status & Info ──
    STATUS("/status", "System health overview", "/status", CommandCategory.STATUS, false),
    ALERTS("/alerts", "Show all active alerts", "/alerts", CommandCategory.STATUS, false),
    ACK("/ack", "Acknowledge an alert", "/ack <alert_id>", CommandCategory.STATUS),
    TOKENS("/tokens", "Show token usage across agents", "/tokens", CommandCategory.STATUS, false),
    PULSE("/pulse", "Show work pulse (activity/min)", "/pulse <agent_id>", CommandCategory.STATUS),
    LOG("/log", "Show recent activity log", "/log <agent_id>", CommandCategory.STATUS),

    // ── Commands ──
    CMD("/cmd", "Send a raw command to an agent", "/cmd <agent_id> <command>", CommandCategory.COMMANDS),
    TELL("/tell", "Send a message to an agent", "/tell <agent_id> <message>", CommandCategory.COMMANDS),
    ASK("/ask", "Ask agent a question, wait for response", "/ask <agent_id> <question>", CommandCategory.COMMANDS),

    // ── Connection ──
    CONNECT("/connect", "Connect to a RAAMSES server", "/connect <host:port>", CommandCategory.CONNECTION),
    DISCONNECT("/disconnect", "Disconnect from server", "/disconnect", CommandCategory.CONNECTION, false),
    MOCK("/mock", "Switch to mock/demo data mode", "/mock", CommandCategory.CONNECTION, false),

    // ── Help ──
    HELP("/help", "Show all available commands", "/help", CommandCategory.HELP, false),
    ABOUT("/about", "About RAAMSES Console", "/about", CommandCategory.HELP, false);
}

enum class CommandCategory(val label: String) {
    AGENTS("Agent Control"),
    STATUS("Status & Info"),
    COMMANDS("Commands"),
    CONNECTION("Connection"),
    HELP("Help")
}

data class GatewayMessage(
    val id: String,
    val text: String,
    val isFromUser: Boolean,      // true = user command, false = server response
    val timestamp: Long,
    val command: SlashCommand? = null,
    val isError: Boolean = false
)

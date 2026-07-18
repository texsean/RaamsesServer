package com.raamses.console.data

import com.raamses.console.data.models.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.UUID

/**
 * Provides realistic mock data for development/testing without a live server.
 * Uses the same schema shapes as the Python protocol layer.
 */
class MockDataProvider {

    private val now = System.currentTimeMillis() / 1000

    private val _agents = MutableStateFlow(generateMockAgents())
    val agents: StateFlow<List<AgentStatus>> = _agents.asStateFlow()

    private val _alerts = MutableStateFlow(generateMockAlerts())
    val alerts: StateFlow<List<ConsoleAlert>> = _alerts.asStateFlow()

    private val _serverHealth = MutableStateFlow(generateMockHealth())
    val serverHealth: StateFlow<ServerHealth> = _serverHealth.asStateFlow()

    fun refresh() {
        _agents.value = generateMockAgents()
        _alerts.value = generateMockAlerts()
        _serverHealth.value = generateMockHealth()
    }

    private fun generateMockAgents(): List<AgentStatus> = listOf(
        AgentStatus(
            agentId = "hermes-gateway-01",
            name = "Gateway Server",
            status = "ACTIVE",
            objective = "Implement Debian gateway registration",
            currentOperation = "Debugging failed TLS handshake test",
            lastVerifiedWork = now - 12,
            lastVerifiedDescription = "Editing: gateway.cpp — clang++ build running",
            tokenUsage = TokenUsageData(total = 142_300, lastHour = 8_200, today = 47_800),
            subAgentCount = 2,
            needsHumanInput = false,
            verifiedCompletion = 0.48f,
            reportedCompletion = 0.85f,
            checklist = listOf(
                ChecklistItem("Configuration loader", ItemStatus.DONE),
                ChecklistItem("HTTP listener", ItemStatus.DONE),
                ChecklistItem("Console registration", ItemStatus.IN_PROGRESS),
                ChecklistItem("Heartbeat handling", ItemStatus.IN_PROGRESS),
                ChecklistItem("TLS validation", ItemStatus.PENDING),
                ChecklistItem("systemd installer", ItemStatus.PENDING)
            ),
            recentActivity = listOf(
                ActivityEvent(now - 23, ActivityType.FILE_READ, "protocol.xsd", null),
                ActivityEvent(now - 18, ActivityType.FILE_WRITE, "gateway.cpp", "+412/-96 lines"),
                ActivityEvent(now - 14, ActivityType.COMPILER_RUN, "cmake --build", "exit 0"),
                ActivityEvent(now - 5, ActivityType.TEST_EXEC, "gateway tests", "18 passed, 2 failed"),
                ActivityEvent(now - 2, ActivityType.FILE_WRITE, "gateway_tests.cpp", "+34/-2 lines")
            ),
            workPulse = listOf(1,2,3,7,6,5,7,2,1,1,3,6,7,5,3,1, 0,1,2,5,7,6,4,3,2,2,4,6,7,5,4,2, 1,2,3,5,7,6,4,3,2,3,5,7,7,5,3,2, 1,2,4,5,7,6,5,3,2,3,5,7)
        ),
        AgentStatus(
            agentId = "claude-code-01",
            name = "Claude Code",
            status = "ACTIVE",
            objective = "Add OAuth2 support to API layer",
            currentOperation = "Writing token refresh logic",
            lastVerifiedWork = now - 4,
            lastVerifiedDescription = "Writing: auth/refresh.rs — cargo check running",
            tokenUsage = TokenUsageData(total = 89_700, lastHour = 5_100, today = 31_200),
            subAgentCount = 1,
            needsHumanInput = false,
            verifiedCompletion = 0.72f,
            reportedCompletion = 0.80f,
            checklist = listOf(
                ChecklistItem("Token endpoint", ItemStatus.DONE),
                ChecklistItem("Refresh flow", ItemStatus.IN_PROGRESS),
                ChecklistItem("Scope validation", ItemStatus.DONE),
                ChecklistItem("Error handling", ItemStatus.PENDING)
            ),
            recentActivity = listOf(
                ActivityEvent(now - 15, ActivityType.FILE_READ, "auth/mod.rs", null),
                ActivityEvent(now - 8, ActivityType.FILE_WRITE, "auth/refresh.rs", "+87/-12 lines"),
                ActivityEvent(now - 4, ActivityType.COMPILER_RUN, "cargo check", "exit 0")
            ),
            workPulse = listOf(0,0,1,3,5,4,4,3,2,2,5,6,5,4,2,1, 1,2,3,5,4,3,2,1,2,3,4,5,4,3,2,1, 2,3,4,5,4,3,2,2,3,4,5,4,3,2,1,1, 2,3,4,5,4,3,2,2,3,4,4,3)
        ),
        AgentStatus(
            agentId = "hermes-pi-agent",
            name = "Pi Build Agent",
            status = "BLOCKED",
            objective = "Cross-compile ESP32 firmware",
            currentOperation = "Awaiting user: select target board variant",
            lastVerifiedWork = now - 420,
            lastVerifiedDescription = "cmake: board variant not specified",
            tokenUsage = TokenUsageData(total = 12_400, lastHour = 0, today = 3_100),
            subAgentCount = 0,
            needsHumanInput = true,
            verifiedCompletion = 0.35f,
            reportedCompletion = 0.35f,
            checklist = listOf(
                ChecklistItem("Toolchain setup", ItemStatus.DONE),
                ChecklistItem("Base firmware compile", ItemStatus.DONE),
                ChecklistItem("Board variant config", ItemStatus.PENDING),
                ChecklistItem("Flash script", ItemStatus.PENDING)
            ),
            recentActivity = listOf(
                ActivityEvent(now - 420, ActivityType.SHELL_CMD, "cmake --preset esp32-s3", "BOARD not set"),
                ActivityEvent(now - 425, ActivityType.USER_INPUT, "Awaiting board selection", null)
            ),
            workPulse = List(60) { 0 }
        ),
        AgentStatus(
            agentId = "grok-research",
            name = "Grok Research",
            status = "QUIET",
            objective = "Market research: agent monitoring tools",
            currentOperation = "Compiling competitor analysis",
            lastVerifiedWork = now - 180,
            lastVerifiedDescription = "Writing: research/competitors.md",
            tokenUsage = TokenUsageData(total = 56_200, lastHour = 2_100, today = 18_500),
            subAgentCount = 0,
            needsHumanInput = false,
            verifiedCompletion = 0.65f,
            reportedCompletion = 0.70f,
            checklist = listOf(
                ChecklistItem("Competitor landscape", ItemStatus.DONE),
                ChecklistItem("Pricing analysis", ItemStatus.DONE),
                ChecklistItem("Feature matrix", ItemStatus.IN_PROGRESS),
                ChecklistItem("SWOT analysis", ItemStatus.PENDING)
            ),
            recentActivity = listOf(
                ActivityEvent(now - 180, ActivityType.FILE_WRITE, "research/competitors.md", "+156/-23 lines")
            ),
            workPulse = List(60) { i -> if (i < 5) 1 else 0 }
        )
    )

    private fun generateMockAlerts(): List<ConsoleAlert> = listOf(
        ConsoleAlert(
            id = UUID.randomUUID().toString(),
            severity = "critical",
            title = "Agent Blocked",
            message = "Pi Build Agent awaiting board variant selection for 7 minutes",
            timestamp = now - 420,
            requiresAck = true
        ),
        ConsoleAlert(
            id = UUID.randomUUID().toString(),
            severity = "warning",
            title = "Report Mismatch",
            message = "Gateway Server claims 85% complete; verified tasks indicate 48%",
            timestamp = now - 60,
            requiresAck = false
        ),
        ConsoleAlert(
            id = UUID.randomUUID().toString(),
            severity = "info",
            title = "Test Failures",
            message = "Gateway: 18 passed, 2 failed — gateway_tests.cpp",
            timestamp = now - 5,
            requiresAck = false
        )
    )

    private fun generateMockHealth(): ServerHealth = ServerHealth(
        cpuPercent = 0.61f,
        memoryPercent = 0.43f,
        diskPercent = 0.28f,
        uptimeSeconds = 86400 * 3 + 14400,
        agentCount = 4,
        activeAgentCount = 2,
        blockedAgentCount = 1
    )
}

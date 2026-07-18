package com.raamses.console.data.models

/**
 * Domain-level models for the console UI.
 * These enrich the wire protocol models with UI-specific state.
 */

data class AgentStatus(
    val agentId: String,
    val name: String,
    val status: String,              // ACTIVE, QUIET, IDLE, STALE, BLOCKED, UNVERIFIED
    val objective: String? = null,
    val currentOperation: String? = null,
    val lastVerifiedWork: Long? = null,    // epoch seconds
    val lastVerifiedDescription: String? = null,
    val tokenUsage: TokenUsageData? = null,
    val subAgentCount: Int = 0,
    val needsHumanInput: Boolean = false,
    val verifiedCompletion: Float = 0f,    // 0.0 - 1.0
    val reportedCompletion: Float = 0f,
    val checklist: List<ChecklistItem> = emptyList(),
    val recentActivity: List<ActivityEvent> = emptyList(),
    val workPulse: List<Int> = emptyList() // events per minute, last 60
)

data class TokenUsageData(
    val total: Long = 0,
    val lastHour: Long = 0,
    val today: Long = 0
)

data class ChecklistItem(
    val label: String,
    val status: ItemStatus = ItemStatus.PENDING
)

enum class ItemStatus { DONE, IN_PROGRESS, PENDING, FAILED }

data class ActivityEvent(
    val timestamp: Long,              // epoch seconds
    val type: ActivityType,
    val description: String,
    val detail: String? = null        // e.g. "+412/-96 lines", "37/39 pass"
)

enum class ActivityType {
    FILE_READ, FILE_WRITE, SHELL_CMD, COMPILER_RUN,
    TEST_EXEC, GIT_DIFF, COMMIT, API_CALL, AGENT_RESPONSE, USER_INPUT
}

data class ServerHealth(
    val cpuPercent: Float,
    val memoryPercent: Float,
    val diskPercent: Float,
    val uptimeSeconds: Long,
    val agentCount: Int,
    val activeAgentCount: Int,
    val blockedAgentCount: Int
)

data class ConsoleAlert(
    val id: String,
    val severity: String,
    val title: String,
    val message: String,
    val timestamp: Long,
    val requiresAck: Boolean = false,
    val acknowledged: Boolean = false
)

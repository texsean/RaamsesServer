package com.raamses.console.data.models

import kotlinx.serialization.Serializable

// ── Envelope (matches Python RaamsesMessage) ──

@Serializable
data class RaamsesHeader(
    val message_id: String,
    val timestamp: String,     // ISO 8601 UTC
    val device_id: String,
    val schema_version: String = "1.0",
    val version: String = "1.0"
)

@Serializable
data class RaamsesEnvelope(
    val header: RaamsesHeader,
    val payload: String         // JSON-encoded payload, deserialized by type
)

// ── Register ──

@Serializable
data class Capabilities(
    val screen: Map<String, String>? = null,
    val input: Map<String, String>? = null,
    val output: Map<String, String>? = null,
    val power: Map<String, String>? = null
)

@Serializable
data class RegisterMessage(
    val device_id: String,
    val schema_version: String,
    val device_type: String,
    val firmware_version: String? = null,
    val capabilities: Capabilities? = null
)

@Serializable
data class RegisterAck(
    val accepted: Boolean,
    val server_time: String,
    val schema_version: String? = null,
    val assigned_tier: String? = null,
    val error_message: String? = null
)

// ── Heartbeat ──

@Serializable
data class Heartbeat(
    val uptime_seconds: Long,
    val battery_percent: Int? = null,
    val signal_strength: Int? = null,
    val free_memory_kb: Long? = null
)

// ── Alert ──

@Serializable
data class Alert(
    val severity: String,       // "info", "warning", "critical"
    val title: String,
    val message: String,
    val requires_ack: Boolean? = null,
    val vibrate: Boolean? = null
)

// ── Command ──

@Serializable
data class Command(
    val command_id: String,
    val action: String,
    val payload: String? = null
)

@Serializable
data class CommandResult(
    val command_id: String,
    val success: Boolean,
    val message: String? = null
)

// ── Agent Update ──

@Serializable
data class TokenUsage(
    val total: Long? = null,
    val last_hour: Long? = null,
    val today: Long? = null
)

@Serializable
data class AgentUpdate(
    val agent_id: String,
    val status: String,              // "ACTIVE", "QUIET", "IDLE", "STALE", "BLOCKED", "UNVERIFIED"
    val token_usage: TokenUsage? = null,
    val sub_agent_count: Int? = null,
    val needs_human_input: Boolean? = null
)

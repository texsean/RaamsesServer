package com.raamses.console.ui.agents

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.raamses.console.data.models.*
import com.raamses.console.ui.components.*
import com.raamses.console.ui.theme.*

@Composable
fun AgentDetailScreen(
    agent: AgentStatus,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(Background),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // ── Header ──
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                TextButton(onClick = onBack) {
                    Text("< BACK", color = AccentBlue, style = MaterialTheme.typography.labelMedium)
                }
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = agent.name,
                        style = MaterialTheme.typography.headlineMedium,
                        color = TextPrimary
                    )
                    Text(
                        text = agent.agentId,
                        style = MaterialTheme.typography.bodySmall,
                        color = TextMuted
                    )
                }
                StatusIndicator(agent.status)
            }
        }

        // ── Objective & Operation ──
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = CardBackground)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("OBJECTIVE", style = MaterialTheme.typography.labelMedium, color = TextMuted)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = agent.objective ?: "No objective set",
                        style = MaterialTheme.typography.titleMedium,
                        color = TextPrimary
                    )

                    if (agent.currentOperation != null) {
                        Spacer(Modifier.height(12.dp))
                        Text("CURRENT OPERATION", style = MaterialTheme.typography.labelMedium, color = TextMuted)
                        Spacer(Modifier.height(4.dp))
                        Text(
                            text = agent.currentOperation,
                            style = MaterialTheme.typography.bodyLarge,
                            color = AccentBlue
                        )
                    }

                    agent.lastVerifiedWork?.let {
                        Spacer(Modifier.height(12.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("LAST VERIFIED WORK", style = MaterialTheme.typography.labelMedium, color = TextMuted)
                            Text(
                                text = formatSecondsAgo(it),
                                style = MaterialTheme.typography.labelMedium,
                                color = StatusActive
                            )
                        }
                        agent.lastVerifiedDescription?.let { desc ->
                            Spacer(Modifier.height(4.dp))
                            Text(text = desc, style = MaterialTheme.typography.bodyMedium, color = TextSecondary)
                        }
                    }
                }
            }
        }

        // ── Token Usage ──
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = CardBackground)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("TOKEN USAGE", style = MaterialTheme.typography.labelMedium, color = TextMuted)
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                        agent.tokenUsage?.let { tokens ->
                            TokenBadge("TODAY", tokens.today)
                            TokenBadge("LAST HOUR", tokens.lastHour)
                            TokenBadge("TOTAL", tokens.total)
                        } ?: Text("No data", style = MaterialTheme.typography.bodyMedium, color = TextMuted)
                    }
                }
            }
        }

        // ── Evidence-Backed Completion ──
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = CardBackground)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("COMPLETION", style = MaterialTheme.typography.labelMedium, color = TextMuted)
                        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            Text(
                                text = "Verified: ${(agent.verifiedCompletion * 100).toInt()}%",
                                style = MaterialTheme.typography.labelMedium,
                                color = StatusActive
                            )
                            Text(
                                text = "Reported: ${(agent.reportedCompletion * 100).toInt()}%",
                                style = MaterialTheme.typography.labelMedium,
                                color = if (agent.reportedCompletion != agent.verifiedCompletion) SeverityWarning else TextSecondary
                            )
                        }
                    }

                    if (agent.reportedCompletion != agent.verifiedCompletion) {
                        Spacer(Modifier.height(8.dp))
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = SeverityWarning.copy(alpha = 0.15f)
                        ) {
                            Text(
                                text = "⚠ REPORT MISMATCH — Agent claims ${(agent.reportedCompletion * 100).toInt()}%; verified tasks indicate ${(agent.verifiedCompletion * 100).toInt()}%",
                                style = MaterialTheme.typography.bodySmall,
                                color = SeverityWarning,
                                modifier = Modifier.padding(8.dp)
                            )
                        }
                    }

                    // Checklist
                    if (agent.checklist.isNotEmpty()) {
                        Spacer(Modifier.height(12.dp))
                        agent.checklist.forEach { item ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                val (icon, color) = when (item.status) {
                                    ItemStatus.DONE -> "✓" to StatusActive
                                    ItemStatus.IN_PROGRESS -> "~" to AccentBlue
                                    ItemStatus.PENDING -> " " to TextMuted
                                    ItemStatus.FAILED -> "✗" to SeverityCritical
                                }
                                Text(
                                    text = "[$icon]",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = color,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.width(28.dp)
                                )
                                Text(
                                    text = item.label,
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = if (item.status == ItemStatus.PENDING) TextMuted else TextPrimary
                                )
                            }
                        }
                    }
                }
            }
        }

        // ── Work Pulse ──
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = CardBackground)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("WORK PULSE — LAST 60 MIN", style = MaterialTheme.typography.labelMedium, color = TextMuted)
                    Spacer(Modifier.height(8.dp))
                    WorkPulseGraph(pulse = agent.workPulse)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = "▁ events/min",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextMuted
                    )
                }
            }
        }

        // ── Recent Activity ──
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = CardBackground)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("RECENT ACTIVITY", style = MaterialTheme.typography.labelMedium, color = TextMuted)
                    Spacer(Modifier.height(8.dp))
                    agent.recentActivity.take(8).forEach { event ->
                        ActivityFeedItem(event)
                    }
                    if (agent.recentActivity.isEmpty()) {
                        Text("No recent activity", style = MaterialTheme.typography.bodyMedium, color = TextMuted)
                    }
                }
            }
        }

        // ── Quick Commands ──
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = CardBackground)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("QUICK COMMANDS", style = MaterialTheme.typography.labelMedium, color = TextMuted)
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(
                            "/approve ${agent.agentId}" to AccentGreen,
                            "/pause ${agent.agentId}" to AccentOrange,
                            "/restart ${agent.agentId}" to AccentBlue,
                            "/stop ${agent.agentId}" to AccentRed
                        ).forEach { (cmd, color) ->
                            SuggestionChip(
                                onClick = { /* TODO: send command */ },
                                label = { Text(cmd, style = MaterialTheme.typography.bodySmall, color = color) },
                                colors = SuggestionChipDefaults.suggestionChipColors(containerColor = SurfaceVariant),
                                border = null
                            )
                        }
                    }
                }
            }
        }

        item { Spacer(Modifier.height(72.dp)) }
    }
}

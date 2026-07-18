package com.raamses.console.ui.dashboard

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
fun DashboardScreen(
    agents: List<AgentStatus>,
    serverHealth: ServerHealth,
    alerts: List<ConsoleAlert>,
    onAgentClick: (String) -> Unit,
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
            Text(
                text = "RAAMSES CONSOLE",
                style = MaterialTheme.typography.headlineMedium,
                color = AccentBlue,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = "Agent Operations Dashboard",
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary
            )
        }

        // ── System Status Bar ──
        item {
            SystemStatusBar(serverHealth)
        }

        // ── Agent Cards ──
        item {
            Text(
                text = "AGENTS (${agents.size})",
                style = MaterialTheme.typography.titleMedium,
                color = TextPrimary,
                modifier = Modifier.padding(top = 8.dp)
            )
        }

        items(agents, key = { it.agentId }) { agent ->
            AgentStatusCard(
                agent = agent,
                onClick = { onAgentClick(agent.agentId) }
            )
        }

        // ── Active Alerts ──
        if (alerts.isNotEmpty()) {
            item {
                Text(
                    text = "ALERTS (${alerts.size})",
                    style = MaterialTheme.typography.titleMedium,
                    color = TextPrimary,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
            items(alerts.take(3), key = { it.id }) { alert ->
                AlertCard(alert = alert)
            }
        }

        // ── Spacer for nav bar ──
        item { Spacer(Modifier.height(72.dp)) }
    }
}

@Composable
private fun SystemStatusBar(health: ServerHealth) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Surface)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            StatusChip("CPU", "${(health.cpuPercent * 100).toInt()}%", if (health.cpuPercent > 0.8f) SeverityWarning else AccentGreen)
            StatusChip("MEM", "${(health.memoryPercent * 100).toInt()}%", if (health.memoryPercent > 0.8f) SeverityWarning else AccentGreen)
            StatusChip("DISK", "${(health.diskPercent * 100).toInt()}%", if (health.diskPercent > 0.85f) SeverityWarning else AccentGreen)
            StatusChip("UP", formatUptime(health.uptimeSeconds), TextSecondary)
        }
        Divider(color = Border, thickness = 0.5.dp)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            StatItem("AGENTS", "${health.agentCount}")
            StatItem("ACTIVE", "${health.activeAgentCount}", StatusActive)
            StatItem("BLOCKED", "${health.blockedAgentCount}", if (health.blockedAgentCount > 0) StatusBlocked else TextMuted)
        }
    }
}

@Composable
private fun StatusChip(label: String, value: String, color: androidx.compose.ui.graphics.Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(text = value, style = MaterialTheme.typography.titleMedium, color = color, fontWeight = FontWeight.Bold)
        Text(text = label, style = MaterialTheme.typography.bodySmall, color = TextMuted)
    }
}

@Composable
private fun StatItem(label: String, value: String, color: androidx.compose.ui.graphics.Color = TextPrimary) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(text = value, style = MaterialTheme.typography.titleMedium, color = color, fontWeight = FontWeight.Bold)
        Text(text = label, style = MaterialTheme.typography.bodySmall, color = TextMuted)
    }
}

private fun formatUptime(seconds: Long): String = when {
    seconds >= 86400 -> "${seconds / 86400}d"
    seconds >= 3600 -> "${seconds / 3600}h"
    else -> "${seconds / 60}m"
}

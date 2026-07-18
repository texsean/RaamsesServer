package com.raamses.console.ui.components

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.raamses.console.data.models.AgentStatus
import com.raamses.console.ui.theme.*

@Composable
fun StatusIndicator(status: String, modifier: Modifier = Modifier) {
    val color = when (status) {
        "ACTIVE" -> StatusActive
        "QUIET" -> StatusQuiet
        "IDLE" -> StatusIdle
        "STALE" -> StatusStale
        "BLOCKED" -> StatusBlocked
        "UNVERIFIED" -> StatusUnverified
        else -> TextMuted
    }

    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(color)
        )
        Spacer(Modifier.width(6.dp))
        Text(
            text = status,
            style = MaterialTheme.typography.labelMedium,
            color = color,
            fontWeight = FontWeight.Bold
        )
    }
}

@Composable
fun AgentStatusCard(
    agent: AgentStatus,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = CardBackground)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clickable(onClick = onClick)
                .padding(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = agent.name,
                        style = MaterialTheme.typography.titleMedium,
                        color = TextPrimary,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = agent.agentId,
                        style = MaterialTheme.typography.bodySmall,
                        color = TextMuted
                    )
                }
                StatusIndicator(agent.status)
            }

            if (agent.currentOperation != null) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = agent.currentOperation,
                    style = MaterialTheme.typography.bodySmall,
                    color = TextSecondary,
                    maxLines = 1
                )
            }

            Spacer(Modifier.height(8.dp))

            // Last verified work
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "LAST VERIFIED: ${agent.lastVerifiedDescription ?: "N/A"}",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted,
                    maxLines = 1,
                    modifier = Modifier.weight(1f)
                )
                agent.lastVerifiedWork?.let {
                    Text(
                        text = formatSecondsAgo(it),
                        style = MaterialTheme.typography.bodySmall,
                        color = StatusActive
                    )
                }
            }

            // Progress bar (verified vs reported)
            if (agent.verifiedCompletion > 0 || agent.reportedCompletion > 0) {
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "${(agent.verifiedCompletion * 100).toInt()}% verified",
                        style = MaterialTheme.typography.bodySmall,
                        color = StatusActive,
                        modifier = Modifier.width(80.dp)
                    )
                    LinearProgressIndicator(
                        progress = { agent.verifiedCompletion },
                        modifier = Modifier
                            .weight(1f)
                            .height(4.dp)
                            .clip(RoundedCornerShape(2.dp)),
                        color = StatusActive,
                        trackColor = SurfaceVariant
                    )
                }
                if (agent.reportedCompletion != agent.verifiedCompletion) {
                    Spacer(Modifier.height(2.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = "${(agent.reportedCompletion * 100).toInt()}% reported",
                            style = MaterialTheme.typography.bodySmall,
                            color = SeverityWarning,
                            modifier = Modifier.width(80.dp)
                        )
                        Text(
                            text = "⚠ MISMATCH",
                            style = MaterialTheme.typography.bodySmall,
                            color = SeverityWarning,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }

            // Token usage
            agent.tokenUsage?.let { tokens ->
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    TokenBadge("TODAY", tokens.today)
                    TokenBadge("1HR", tokens.lastHour)
                    TokenBadge("TOTAL", tokens.total)
                }
            }

            // Needs input badge
            if (agent.needsHumanInput) {
                Spacer(Modifier.height(8.dp))
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = StatusBlocked.copy(alpha = 0.2f)
                ) {
                    Text(
                        text = "NEEDS HUMAN INPUT",
                        style = MaterialTheme.typography.labelMedium,
                        color = StatusBlocked,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }
        }
    }
}

@Composable
fun TokenBadge(label: String, value: Long) {
    Column {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = TextMuted
        )
        Text(
            text = formatTokenCount(value),
            style = MaterialTheme.typography.labelMedium,
            color = TextSecondary
        )
    }
}

@Composable
fun WorkPulseGraph(
    pulse: List<Int>,
    modifier: Modifier = Modifier,
    barColor: androidx.compose.ui.graphics.Color = AccentGreen
) {
    if (pulse.isEmpty()) return

    val maxVal = pulse.max().coerceAtLeast(1)

    Row(
        modifier = modifier
            .fillMaxWidth()
            .height(32.dp),
        horizontalArrangement = Arrangement.spacedBy(1.dp),
        verticalAlignment = Alignment.Bottom
    ) {
        pulse.forEach { value ->
            val heightFraction = value.toFloat() / maxVal
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight(heightFraction.coerceIn(0.05f, 1f))
                    .clip(RoundedCornerShape(1.dp))
                    .background(if (value > 0) barColor else SurfaceVariant)
            )
        }
    }
}

@Composable
fun ActivityFeedItem(
    event: com.raamses.console.data.models.ActivityEvent,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = formatTimestamp(event.timestamp),
            style = MaterialTheme.typography.bodySmall,
            color = TextMuted,
            modifier = Modifier.width(60.dp)
        )
        Text(
            text = event.type.name.replace("_", " "),
            style = MaterialTheme.typography.labelMedium,
            color = when (event.type) {
                com.raamses.console.data.models.ActivityType.FILE_WRITE -> AccentGreen
                com.raamses.console.data.models.ActivityType.TEST_EXEC -> AccentBlue
                com.raamses.console.data.models.ActivityType.COMPILER_RUN -> AccentOrange
                com.raamses.console.data.models.ActivityType.USER_INPUT -> StatusBlocked
                else -> TextSecondary
            },
            modifier = Modifier.width(72.dp)
        )
        Text(
            text = event.description,
            style = MaterialTheme.typography.bodySmall,
            color = TextPrimary,
            maxLines = 1
        )
        if (event.detail != null) {
            Spacer(Modifier.width(4.dp))
            Text(
                text = event.detail,
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
                maxLines = 1
            )
        }
    }
}

@Composable
fun AlertCard(
    alert: com.raamses.console.data.models.ConsoleAlert,
    onAck: (() -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    val severityColor = when (alert.severity) {
        "critical" -> SeverityCritical
        "warning" -> SeverityWarning
        else -> SeverityInfo
    }

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = severityColor.copy(alpha = 0.1f))
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.Top
        ) {
            Box(
                modifier = Modifier
                    .width(3.dp)
                    .height(40.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(severityColor)
            )
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = alert.title,
                        style = MaterialTheme.typography.titleMedium,
                        color = TextPrimary,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = formatSecondsAgo(alert.timestamp),
                        style = MaterialTheme.typography.bodySmall,
                        color = TextMuted
                    )
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    text = alert.message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary
                )
                if (alert.requiresAck && !alert.acknowledged && onAck != null) {
                    Spacer(Modifier.height(8.dp))
                    TextButton(onClick = onAck) {
                        Text("ACKNOWLEDGE", color = severityColor, style = MaterialTheme.typography.labelMedium)
                    }
                }
            }
        }
    }
}

// ── Utility Formatters ──

fun formatSecondsAgo(epoch: Long): String {
    val diff = (System.currentTimeMillis() / 1000) - epoch
    return when {
        diff < 60 -> "${diff}s"
        diff < 3600 -> "${diff / 60}m"
        diff < 86400 -> "${diff / 3600}h"
        else -> "${diff / 86400}d"
    }
}

fun formatTimestamp(epoch: Long): String {
    val diff = (System.currentTimeMillis() / 1000) - epoch
    return when {
        diff < 60 -> "now"
        diff < 3600 -> "${diff / 60}m ago"
        else -> "${diff / 3600}h ago"
    }
}

fun formatTokenCount(count: Long): String = when {
    count >= 1_000_000 -> "${count / 1_000_000}.${(count % 1_000_000) / 100_000}M"
    count >= 1_000 -> "${count / 1_000}.${(count % 1_000) / 100}K"
    else -> count.toString()
}

// Local clickable composable helper
@Composable
private fun Modifier.clickable(onClick: () -> Unit): Modifier =
    this.then(androidx.compose.foundation.clickable { onClick() })

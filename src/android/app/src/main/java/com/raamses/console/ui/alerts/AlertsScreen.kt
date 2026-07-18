package com.raamses.console.ui.alerts

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.raamses.console.data.models.ConsoleAlert
import com.raamses.console.ui.components.AlertCard
import com.raamses.console.ui.theme.*

@Composable
fun AlertsScreen(
    alerts: List<ConsoleAlert>,
    onAck: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(Background),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        item {
            Text(
                text = "ALERTS",
                style = MaterialTheme.typography.headlineMedium,
                color = TextPrimary,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(4.dp))
            val unacked = alerts.count { !it.acknowledged }
            Text(
                text = "$unacked unacknowledged, ${alerts.size} total",
                style = MaterialTheme.typography.bodyMedium,
                color = if (unacked > 0) SeverityWarning else TextSecondary
            )
        }

        if (alerts.isEmpty()) {
            item {
                Spacer(Modifier.height(48.dp))
                Text(
                    text = "No active alerts",
                    style = MaterialTheme.typography.bodyLarge,
                    color = TextMuted,
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }

        items(alerts, key = { it.id }) { alert ->
            AlertCard(
                alert = alert,
                onAck = if (alert.requiresAck && !alert.acknowledged) {
                    { onAck(alert.id) }
                } else null
            )
        }

        item { Spacer(Modifier.height(72.dp)) }
    }
}

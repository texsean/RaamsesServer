package com.raamses.console.ui.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.raamses.console.data.MockDataProvider
import com.raamses.console.data.models.*
import com.raamses.console.ui.agents.AgentDetailScreen
import com.raamses.console.ui.alerts.AlertsScreen
import com.raamses.console.ui.dashboard.DashboardScreen
import com.raamses.console.ui.gateway.GatewayMessage
import com.raamses.console.ui.gateway.GatewayScreen
import java.util.UUID

sealed class Screen(val route: String, val label: String, val icon: ImageVector) {
    data object Gateway : Screen("gateway", "Gateway", Icons.Default.Terminal)
    data object Dashboard : Screen("dashboard", "Dashboard", Icons.Default.Dashboard)
    data object Alerts : Screen("alerts", "Alerts", Icons.Default.Notifications)
    data object AgentDetail : Screen("agent/{agentId}", "Agent", Icons.Default.Computer) {
        fun createRoute(agentId: String) = "agent/$agentId"
    }
}

val bottomNavItems = listOf(Screen.Gateway, Screen.Dashboard, Screen.Alerts)

@Composable
fun RaamsesNavHost(
    mockProvider: MockDataProvider,
    modifier: Modifier = Modifier
) {
    val navController = rememberNavController()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    val agents by mockProvider.agents.collectAsState()
    val alerts by mockProvider.alerts.collectAsState()
    val serverHealth by mockProvider.serverHealth.collectAsState()

    // Gateway messages state
    var gatewayMessages by remember { mutableStateOf(listOf<GatewayMessage>()) }
    var isConnected by remember { mutableStateOf(false) }

    // Show bottom bar only on main tabs
    val showBottomBar = currentRoute in bottomNavItems.map { it.route }

    Scaffold(
        modifier = modifier,
        bottomBar = {
            if (showBottomBar) {
                NavigationBar(
                    containerColor = Surface,
                    contentColor = TextPrimary
                ) {
                    bottomNavItems.forEach { screen ->
                        NavigationBarItem(
                            icon = { Icon(screen.icon, contentDescription = screen.label) },
                            label = { Text(screen.label) },
                            selected = currentRoute == screen.route,
                            onClick = {
                                if (currentRoute != screen.route) {
                                    navController.navigate(screen.route) {
                                        popUpTo(Screen.Gateway.route) { saveState = true }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                }
                            },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = AccentBlue,
                                selectedTextColor = AccentBlue,
                                unselectedIconColor = TextMuted,
                                unselectedTextColor = TextMuted,
                                indicatorColor = AccentBlue.copy(alpha = 0.15f)
                            )
                        )
                    }
                }
            }
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = Screen.Gateway.route,
            modifier = Modifier.padding(innerPadding)
        ) {
            composable(Screen.Gateway.route) {
                GatewayScreen(
                    messages = gatewayMessages,
                    onSendCommand = { command ->
                        val msg = GatewayMessage(
                            id = UUID.randomUUID().toString(),
                            text = command,
                            isFromUser = true,
                            timestamp = System.currentTimeMillis() / 1000
                        )
                        gatewayMessages = gatewayMessages + msg
                        // Simulate response from mock
                        val response = processMockCommand(command, mockProvider)
                        gatewayMessages = gatewayMessages + response
                    },
                    isConnected = isConnected,
                    onConnectClick = {
                        isConnected = true
                        mockProvider.refresh()
                    }
                )
            }

            composable(Screen.Dashboard.route) {
                DashboardScreen(
                    agents = agents,
                    serverHealth = serverHealth,
                    alerts = alerts,
                    onAgentClick = { agentId ->
                        navController.navigate(Screen.AgentDetail.createRoute(agentId))
                    }
                )
            }

            composable(Screen.Alerts.route) {
                AlertsScreen(
                    alerts = alerts,
                    onAck = { alertId ->
                        // In real impl, send /ack command to server
                    }
                )
            }

            composable(
                route = Screen.AgentDetail.route,
                arguments = listOf(navArgument("agentId") { type = NavType.StringType })
            ) { backStackEntry ->
                val agentId = backStackEntry.arguments?.getString("agentId") ?: return@composable
                val agent = agents.find { it.agentId == agentId }
                if (agent != null) {
                    AgentDetailScreen(
                        agent = agent,
                        onBack = { navController.popBackStack() }
                    )
                }
            }
        }
    }
}

/**
 * Processes mock slash commands and returns a simulated server response.
 * In production, this goes over TCP to the RAAMSES server.
 */
private fun processMockCommand(command: String, mockProvider: MockDataProvider): GatewayMessage {
    val parts = command.split(" ", limit = 3)
    val cmd = parts.getOrElse(0) { "" }
    val arg = parts.getOrElse(1) { "" }
    val rest = parts.getOrElse(2) { "" }

    val responseText = when (cmd) {
        "/agents" -> {
            val agents = mockProvider.agents.value
            agents.joinToString("\n") { a ->
                "  ${statusEmoji(a.status)} ${a.name} (${a.agentId}) — ${a.status}"
            }
        }
        "/status" -> {
            val h = mockProvider.serverHealth.value
            """
            RAAMSES SERVER STATUS
            ─────────────────────
            CPU:     ${(h.cpuPercent * 100).toInt()}%
            Memory:  ${(h.memoryPercent * 100).toInt()}%
            Disk:    ${(h.diskPercent * 100).toInt()}%
            Uptime:  ${formatDuration(h.uptimeSeconds)}
            Agents:  ${h.agentCount} total, ${h.activeAgentCount} active, ${h.blockedAgentCount} blocked
            """.trimIndent()
        }
        "/alerts" -> {
            val alerts = mockProvider.alerts.value
            if (alerts.isEmpty()) "  No active alerts"
            else alerts.joinToString("\n") { a ->
                "  [${a.severity.uppercase()}] ${a.title}: ${a.message}"
            }
        }
        "/agent" -> {
            val agent = mockProvider.agents.value.find { it.agentId == arg }
            if (agent != null) {
                """
                ${agent.name} (${agent.agentId})
                Status: ${agent.status}
                Objective: ${agent.objective ?: "N/A"}
                Current: ${agent.currentOperation ?: "N/A"}
                Tokens: ${agent.tokenUsage?.today ?: 0} today
                Verified: ${(agent.verifiedCompletion * 100).toInt()}% / Reported: ${(agent.reportedCompletion * 100).toInt()}%
                """.trimIndent()
            } else {
                "  Agent '$arg' not found. Use /agents to list."
            }
        }
        "/approve" -> {
            "  ✓ Sent approval to $arg. Awaiting agent response..."
        }
        "/reject" -> {
            "  ✗ Sent rejection to $arg. Agent will re-prompt or abort."
        }
        "/pause" -> {
            "  ⏸ Pause command sent to $arg."
        }
        "/resume" -> {
            "  ▶ Resume command sent to $arg."
        }
        "/stop" -> {
            "  ⏹ Stop command sent to $arg."
        }
        "/restart" -> {
            "  🔄 Restart command sent to $arg."
        }
        "/tokens" -> {
            mockProvider.agents.value.joinToString("\n") { a ->
                "  ${a.name}: ${a.tokenUsage?.today ?: 0} today, ${a.tokenUsage?.total ?: 0} total"
            }
        }
        "/pulse" -> {
            val agent = mockProvider.agents.value.find { it.agentId == arg }
            if (agent != null) {
                "  Work pulse for ${agent.name}: ${agent.workPulse.joinToString(" ")}"
            } else {
                "  Agent '$arg' not found."
            }
        }
        "/help" -> {
            """
            RAAMSES GATEWAY COMMANDS
            ────────────────────────
            Agent Control:
              /agents              List all agents
              /agent <id>          Agent detail
              /approve <id>        Approve action
              /reject <id>         Reject action
              /pause <id>          Pause agent
              /resume <id>         Resume agent
              /stop <id>           Stop agent
              /restart <id>        Restart agent
            
            Status & Info:
              /status              System health
              /alerts              Active alerts
              /ack <id>            Acknowledge alert
              /tokens              Token usage
              /pulse <id>          Work pulse graph
              /log <id>            Activity log
            
            Commands:
              /cmd <id> <cmd>      Raw command
              /tell <id> <msg>     Send message
              /ask <id> <q>        Ask question
            
            Connection:
              /connect <host:port> Connect to server
              /disconnect          Disconnect
              /mock                Demo mode
            """.trimIndent()
        }
        "/connect" -> {
            "  Connecting to $arg..."
        }
        "/mock" -> {
            mockProvider.refresh()
            "  Switched to mock data mode. 4 agents, 3 alerts loaded."
        }
        "/cmd", "/tell", "/ask" -> {
            "  Sent to $arg: $rest"
        }
        "/ack" -> {
            "  Acknowledged alert $arg."
        }
        "/log" -> {
            val agent = mockProvider.agents.value.find { it.agentId == arg }
            if (agent != null) {
                agent.recentActivity.joinToString("\n") { e ->
                    "  ${e.type.name} ${e.description} ${e.detail ?: ""}"
                }
            } else {
                "  Agent '$arg' not found."
            }
        }
        else -> "  Unknown command: $cmd. Type /help for available commands."
    }

    return GatewayMessage(
        id = UUID.randomUUID().toString(),
        text = responseText,
        isFromUser = false,
        timestamp = System.currentTimeMillis() / 1000
    )
}

private fun statusEmoji(status: String): String = when (status) {
    "ACTIVE" -> "🟢"
    "QUIET" -> "🟡"
    "IDLE" -> "⚪"
    "STALE" -> "🟠"
    "BLOCKED" -> "🔴"
    "UNVERIFIED" -> "🟣"
    else -> "⚫"
}

private fun formatDuration(seconds: Long): String {
    val d = seconds / 86400
    val h = (seconds % 86400) / 3600
    val m = (seconds % 3600) / 60
    return "${d}d ${h}h ${m}m"
}

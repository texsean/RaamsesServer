package com.raamses.console.ui.gateway

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.raamses.console.ui.theme.*
import kotlinx.coroutines.launch
import java.util.UUID

@Composable
fun GatewayScreen(
    messages: List<GatewayMessage>,
    onSendCommand: (String) -> Unit,
    isConnected: Boolean,
    serverHost: String = "",
    onConnectClick: () -> Unit = {}
) {
    var inputText by remember { mutableStateOf("") }
    var showSlashMenu by remember { mutableStateOf(false) }
    var slashFilter by remember { mutableStateOf("") }
    val listState = rememberLazyListState()
    val focusRequester = remember { FocusRequester() }
    val coroutineScope = rememberCoroutineScope()
    val focusManager = LocalFocusManager.current

    // Auto-scroll to bottom when new messages arrive
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }

    // Focus input on launch
    LaunchedEffect(Unit) {
        focusRequester.requestFocus()
    }

    // Determine if slash menu should show
    LaunchedEffect(inputText) {
        showSlashMenu = inputText.startsWith("/") && !inputText.contains(" ")
        slashFilter = if (showSlashMenu) inputText.removePrefix("/").lowercase() else ""
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            // ── Connection Bar ──
            ConnectionBar(isConnected, serverHost, onConnectClick)

            // ── Message List ──
            LazyColumn(
                state = listState,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(vertical = 12.dp)
            ) {
                if (messages.isEmpty()) {
                    item {
                        WelcomeMessage()
                    }
                }
                items(messages, key = { it.id }) { msg ->
                    GatewayMessageBubble(msg)
                }
            }

            // ── Slash Command Overlay ──
            if (showSlashMenu && slashFilter.isNotEmpty() && inputText.length > 1) {
                SlashCommandOverlay(
                    filter = slashFilter,
                    onSelect = { cmd ->
                        inputText = cmd.command + " "
                        showSlashMenu = false
                        focusRequester.requestFocus()
                    },
                    onDismiss = { showSlashMenu = false }
                )
            }

            // ── Command Input Bar ──
            CommandInputBar(
                text = inputText,
                onTextChange = { inputText = it },
                onSend = {
                    if (inputText.isNotBlank()) {
                        onSendCommand(inputText.trim())
                        inputText = ""
                        showSlashMenu = false
                    }
                },
                focusRequester = focusRequester,
                isConnected = isConnected
            )
        }
    }
}

@Composable
private fun ConnectionBar(isConnected: Boolean, host: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Surface)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(if (isConnected) StatusActive else StatusBlocked)
            )
            Spacer(Modifier.width(8.dp))
            Text(
                text = if (isConnected) "CONNECTED" else "DISCONNECTED",
                style = MaterialTheme.typography.labelMedium,
                color = if (isConnected) StatusActive else StatusBlocked
            )
            if (isConnected && host.isNotEmpty()) {
                Spacer(Modifier.width(8.dp))
                Text(
                    text = host,
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted
                )
            }
        }
        if (!isConnected) {
            TextButton(onClick = onClick) {
                Text("CONNECT", color = AccentBlue, style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}

@Composable
private fun WelcomeMessage() {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(48.dp))
        Text(
            text = "RAAMSES GATEWAY",
            style = MaterialTheme.typography.displayLarge,
            color = AccentBlue
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = "Agent Command & Control",
            style = MaterialTheme.typography.bodyLarge,
            color = TextSecondary
        )
        Spacer(Modifier.height(24.dp))
        Text(
            text = "Type / for commands",
            style = MaterialTheme.typography.bodyMedium,
            color = TextMuted
        )
        Spacer(Modifier.height(16.dp))
        // Quick command hints
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("/agents", "/status", "/alerts", "/help").forEach { cmd ->
                SuggestionChip(
                    onClick = { /* pre-fill */ },
                    label = {
                        Text(cmd, style = MaterialTheme.typography.bodySmall, color = AccentBlue)
                    },
                    colors = SuggestionChipDefaults.suggestionChipColors(
                        containerColor = SurfaceVariant
                    ),
                    border = null
                )
            }
        }
    }
}

@Composable
private fun GatewayMessageBubble(msg: GatewayMessage) {
    val alignment = if (msg.isFromUser) Alignment.End else Alignment.Start
    val bgColor = if (msg.isFromUser) {
        if (msg.isError) SeverityCritical.copy(alpha = 0.15f) else AccentBlue.copy(alpha = 0.15f)
    } else {
        SurfaceVariant
    }
    val borderColor = if (msg.isFromUser) {
        if (msg.isError) SeverityCritical else AccentBlue
    } else {
        Border
    }

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = alignment
    ) {
        Box(
            modifier = Modifier
                .widthIn(max = 340.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(bgColor)
                .then(
                    Modifier.drawWithBorder(borderColor, RoundedCornerShape(12.dp))
                )
                .padding(12.dp)
        ) {
            Column {
                if (msg.command != null) {
                    Text(
                        text = msg.command.command,
                        style = MaterialTheme.typography.labelMedium,
                        color = SlashHighlight,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(4.dp))
                }
                Text(
                    text = msg.text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (msg.isError) AccentRed else TextPrimary
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = formatTimestamp(msg.timestamp),
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted
                )
            }
        }
    }
}

@Composable
private fun SlashCommandOverlay(
    filter: String,
    onSelect: (SlashCommand) -> Unit,
    onDismiss: () -> Unit
) {
    val filtered = SlashCommand.entries.filter {
        it.command.contains(filter, ignoreCase = true) ||
        it.description.contains(filter, ignoreCase = true)
    }

    if (filtered.isEmpty()) return

    val grouped = filtered.groupBy { it.category }

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp),
        shape = RoundedCornerShape(12.dp),
        color = Surface,
        shadowElevation = 8.dp
    ) {
        Column(modifier = Modifier.padding(8.dp)) {
            grouped.forEach { (category, commands) ->
                Text(
                    text = category.label.uppercase(),
                    style = MaterialTheme.typography.labelMedium,
                    color = TextMuted,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                )
                commands.forEach { cmd ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onSelect(cmd) }
                            .padding(horizontal = 8.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = cmd.command,
                            style = MaterialTheme.typography.bodyMedium,
                            color = SlashHighlight,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.width(100.dp)
                        )
                        Text(
                            text = cmd.description,
                            style = MaterialTheme.typography.bodySmall,
                            color = TextSecondary
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun CommandInputBar(
    text: String,
    onTextChange: (String) -> Unit,
    onSend: () -> Unit,
    focusRequester: FocusRequester,
    isConnected: Boolean
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = CommandBarBackground,
        shadowElevation = 4.dp
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Slash prompt
            Text(
                text = "/",
                style = MaterialTheme.typography.titleLarge,
                color = if (text.startsWith("/")) SlashHighlight else TextMuted,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.width(8.dp))
            BasicTextField(
                value = text,
                onValueChange = onTextChange,
                modifier = Modifier
                    .weight(1f)
                    .focusRequester(focusRequester),
                textStyle = TextStyle(
                    color = TextPrimary,
                    fontSize = 15.sp,
                    fontFamily = MonoFont
                ),
                cursorBrush = SolidColor(CommandCursor),
                singleLine = true,
                decorationBox = { innerTextField ->
                    if (text.isEmpty()) {
                        Text(
                            text = "command...",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextMuted
                        )
                    }
                    innerTextField()
                }
            )
            Spacer(Modifier.width(8.dp))
            // Send button
            IconButton(
                onClick = onSend,
                enabled = text.isNotBlank(),
                modifier = Modifier.size(36.dp)
            ) {
                Text(
                    text = ">",
                    style = MaterialTheme.typography.titleLarge,
                    color = if (text.isNotBlank()) CommandCursor else TextMuted,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}

// ── Utility ──

private fun formatTimestamp(epoch: Long): String {
    val now = System.currentTimeMillis() / 1000
    val diff = now - epoch
    return when {
        diff < 60 -> "${diff}s ago"
        diff < 3600 -> "${diff / 60}m ago"
        diff < 86400 -> "${diff / 3600}h ago"
        else -> "${diff / 86400}d ago"
    }
}

// Simple border drawing — in production use Modifier.border()
@Composable
private fun Modifier.drawWithBorder(color: androidx.compose.ui.graphics.Color, shape: RoundedCornerShape): Modifier =
    this.then(
        Modifier.drawWithContent {
            drawContent()
            drawRoundRect(
                color = color,
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(12.dp.toPx()),
                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 1.dp.toPx())
            )
        }
    )

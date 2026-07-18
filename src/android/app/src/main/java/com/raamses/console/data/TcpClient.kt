package com.raamses.console.data

import com.raamses.console.data.models.*
import io.ktor.network.selector.*
import io.ktor.network.sockets.*
import io.ktor.utils.io.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json
import java.net.InetSocketAddress
import java.util.UUID

/**
 * TCP client connecting to a RAAMSES server.
 * Falls back to MockDataProvider when no server is configured.
 */
class RaamsesTcpClient(
    private val mockProvider: MockDataProvider = MockDataProvider()
) {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected.asStateFlow()

    private val _agents = MutableStateFlow<List<AgentStatus>>(emptyList())
    val agents: StateFlow<List<AgentStatus>> = _agents.asStateFlow()

    private val _alerts = MutableStateFlow<List<ConsoleAlert>>(emptyList())
    val alerts: StateFlow<List<ConsoleAlert>> = _alerts.asStateFlow()

    private val _serverHealth = MutableStateFlow(ServerHealth(0f, 0f, 0f, 0, 0, 0, 0))
    val serverHealth: StateFlow<ServerHealth> = _serverHealth.asStateFlow()

    private var socket: Socket? = null
    private var connectionJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private val deviceId = "android-console-${UUID.randomUUID().toString().take(8)}"

    fun connect(host: String, port: Int = 42000) {
        disconnect()
        connectionJob = scope.launch {
            try {
                val selector = SelectorManager(Dispatchers.IO)
                socket = aSocket(selector).tcp()
                    .connect(InetSocketAddress(host, port))

                _connected.value = true

                // Register as a console device
                val register = RegisterMessage(
                    device_id = deviceId,
                    schema_version = "1.0",
                    device_type = "android_console",
                    capabilities = Capabilities(
                        screen = mapOf("width" to "1080", "height" to "2400", "color_depth" to "32"),
                        input = mapOf("has_touch" to "true"),
                        output = mapOf("has_vibration" to "true")
                    )
                )
                sendMessage("register", json.encodeToString(RegisterMessage.serializer(), register))

                // Read loop
                val input = socket!!.openReadChannel()
                val output = socket!!.openWriteChannel(autoFlush = true)

                while (isActive) {
                    val line = input.readUTF8Line() ?: break
                    processMessage(line)
                }
            } catch (e: Exception) {
                // Connection failed — use mock data
                useMockData()
            } finally {
                _connected.value = false
                socket?.close()
            }
        }
    }

    fun disconnect() {
        connectionJob?.cancel()
        socket?.close()
        _connected.value = false
    }

    fun useMockData() {
        _connected.value = false
        // Sync from mock provider
        scope.launch {
            mockProvider.agents.collect { _agents.value = it }
        }
        scope.launch {
            mockProvider.alerts.collect { _alerts.value = it }
        }
        scope.launch {
            mockProvider.serverHealth.collect { _serverHealth.value = it }
        }
    }

    private suspend fun sendMessage(type: String, payloadJson: String) {
        val envelope = RaamsesEnvelope(
            header = RaamsesHeader(
                message_id = UUID.randomUUID().toString(),
                timestamp = kotlinx.datetime.Clock.System.now().toString(),
                device_id = deviceId,
                schema_version = "1.0"
            ),
            payload = payloadJson
        )
        val output = socket?.openWriteChannel(autoFlush = true) ?: return
        output.writeStringUtf8(json.encodeToString(RaamsesEnvelope.serializer(), envelope) + "\n")
    }

    private fun processMessage(raw: String) {
        try {
            val envelope = json.decodeFromString(RaamsesEnvelope.serializer(), raw)
            when {
                raw.contains("\"agent_update\"") || raw.contains("agent_id") -> {
                    val update = json.decodeFromString(AgentUpdate.serializer(), envelope.payload)
                    // Update local state — in a real implementation this would merge
                }
                raw.contains("\"alert\"") || raw.contains("\"severity\"") -> {
                    val alert = json.decodeFromString(Alert.serializer(), envelope.payload)
                    _alerts.value = _alerts.value + ConsoleAlert(
                        id = envelope.header.message_id,
                        severity = alert.severity,
                        title = alert.title,
                        message = alert.message,
                        timestamp = System.currentTimeMillis() / 1000,
                        requiresAck = alert.requires_ack ?: false
                    )
                }
            }
        } catch (_: Exception) { /* skip malformed messages */ }
    }
}

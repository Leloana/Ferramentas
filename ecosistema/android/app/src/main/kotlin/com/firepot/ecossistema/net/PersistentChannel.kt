package com.firepot.ecossistema.net

import android.content.Context
import android.os.Build
import android.util.Log
import com.firepot.ecossistema.data.PcConfig
import com.firepot.ecossistema.data.Settings
import com.firepot.ecossistema.model.Descriptor
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import net.schmizz.sshj.SSHClient
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStream
import java.nio.charset.StandardCharsets

/** Estado do canal persistente, para a UI refletir (bolinha de presenca). */
enum class ChannelState { OFFLINE, CONNECTING, ONLINE }

/**
 * Canal persistente de baixa latencia (MELHORIAS_APPLE.md proposta A).
 *
 * Mantem UMA sessao SSH viva rodando `agente.py --serve` no PC e escreve os
 * descritores como linhas JSON nela — em vez de abrir uma sessao SSH por evento
 * (o que pagava connect+handshake+auth+cold start a cada handoff). Isso e o que
 * troca a sensacao de "ferramenta" por "instantaneo".
 *
 * - [enqueue] enfileira uma linha; se o canal estiver caido, a linha espera na
 *   fila e e drenada no reconnect (semente da fila offline, proposta F).
 * - [incoming] emite descritores PC->Android empurrados pelo PC (proposta E).
 * - Reconnect automatico com backoff exponencial.
 *
 * Vive enquanto o [com.firepot.ecossistema.service.HandoffForegroundService]
 * estiver ativo (dono do ciclo de vida).
 */
object PersistentChannel {

    private const val TAG = "PersistentChannel"
    private const val BACKOFF_INICIAL_MS = 1_000L
    private const val BACKOFF_MAX_MS = 30_000L
    private const val HEARTBEAT_MS = 20_000L

    private val _state = MutableStateFlow(ChannelState.OFFLINE)
    val state: StateFlow<ChannelState> = _state.asStateFlow()

    /** Descritores PC->Android (a UI/servico decide como abrir cada um). */
    private val _incoming = MutableSharedFlow<Descriptor>(extraBufferCapacity = 16)
    val incoming: SharedFlow<Descriptor> = _incoming.asSharedFlow()

    // Fila de saida — sobrevive a reconexoes (itens enfileirados offline sao
    // drenados quando o canal volta). Criada uma vez, pela vida do processo.
    private val outbox = Channel<String>(Channel.UNLIMITED)

    private val json = Json { ignoreUnknownKeys = true }

    private var supervisor: Job? = null
    @Volatile private var appContext: Context? = null

    /** Identidade do dispositivo no PC (presenca). B/pareamento pode refinar. */
    private val deviceId: String by lazy {
        "${Build.MANUFACTURER}-${Build.MODEL}".replace(Regex("[^A-Za-z0-9_-]"), "_")
    }
    private val deviceName: String by lazy { Build.MODEL ?: "Android" }

    fun start(context: Context) {
        if (supervisor?.isActive == true) return
        appContext = context.applicationContext
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        supervisor = scope.launch { runSupervisor(scope) }
    }

    fun stop() {
        supervisor?.cancel()
        supervisor = null
        _state.value = ChannelState.OFFLINE
    }

    /** Enfileira uma linha JSON (com `\n` implicito) para o PC. */
    fun enqueue(line: String) {
        outbox.trySend(line.trimEnd('\n'))
    }

    fun isOnline(): Boolean = _state.value == ChannelState.ONLINE

    /** Loop supervisor: conecta, bombeia, e reconecta com backoff ao cair. */
    private suspend fun runSupervisor(scope: CoroutineScope) {
        var backoff = BACKOFF_INICIAL_MS
        while (scope.isActive) {
            _state.value = ChannelState.CONNECTING
            val config = configAtual()
            if (config == null || !config.isComplete) {
                _state.value = ChannelState.OFFLINE
                delay(backoff)
                backoff = (backoff * 2).coerceAtMost(BACKOFF_MAX_MS)
                continue
            }
            try {
                conectarEServir(config, scope)
                backoff = BACKOFF_INICIAL_MS // sessao durou; reseta o backoff
            } catch (e: Exception) {
                Log.w(TAG, "Canal caiu: ${e.message}")
            } finally {
                _state.value = ChannelState.OFFLINE
            }
            if (!scope.isActive) break
            delay(backoff)
            backoff = (backoff * 2).coerceAtMost(BACKOFF_MAX_MS)
        }
    }

    /** Abre a sessao SSH viva e fica lendo a stdout do `--serve` ate cair. */
    private suspend fun conectarEServir(config: PcConfig, scope: CoroutineScope) {
        val ssh = SSHClient()
        var escritorJob: Job? = null
        var heartbeatJob: Job? = null
        try {
            // Pinning quando pareado (proposta B); promiscuo no modo legado.
            ssh.addHostKeyVerifier(HostKeyVerifiers.forFingerprint(config.hostKeyFingerprint))
            ssh.connect(config.host, config.port)
            val keys = ssh.loadKeys(config.privateKeyPem, null, null)
            ssh.authPublickey(config.user, keys)

            ssh.startSession().use { session ->
                val cmd = session.exec(remoteCmd(config.agentPath, "--serve"))
                val saida: OutputStream = cmd.outputStream

                // Apresenta-se ao daemon (presenca) antes de qualquer descritor.
                escrever(saida, helloLine())
                _state.value = ChannelState.ONLINE
                Log.i(TAG, "Canal persistente ONLINE")

                escritorJob = scope.launch { drenarOutbox(saida) }
                heartbeatJob = scope.launch { heartbeat() }

                // Loop de leitura (bloqueante): stdout do --serve = mensagens do PC.
                val reader = BufferedReader(InputStreamReader(cmd.inputStream, StandardCharsets.UTF_8))
                while (scope.isActive) {
                    val line = reader.readLine() ?: break // null = canal fechou
                    tratarRecebido(line)
                }
            }
        } finally {
            heartbeatJob?.cancelAndJoin()
            escritorJob?.cancelAndJoin()
            runCatching { ssh.disconnect() }
        }
    }

    private suspend fun drenarOutbox(saida: OutputStream) {
        for (line in outbox) {
            escrever(saida, line)
        }
    }

    private suspend fun heartbeat() {
        while (true) {
            delay(HEARTBEAT_MS)
            outbox.trySend("""{"_ctrl":"ping"}""")
        }
    }

    private fun escrever(saida: OutputStream, line: String) {
        synchronized(saida) {
            saida.write((line + "\n").toByteArray(StandardCharsets.UTF_8))
            saida.flush()
        }
    }

    private fun tratarRecebido(line: String) {
        val t = line.trim()
        if (t.isEmpty() || t[0] != '{') return
        val obj = runCatching { json.parseToJsonElement(t).jsonObject }.getOrNull() ?: return
        val ctrl = obj["_ctrl"]?.let { runCatching { it.jsonPrimitive.content }.getOrNull() }
        when (ctrl) {
            "pong", "ack" -> { /* keepalive/confirmacao: nada a fazer */ }
            "push" -> {
                val desc = obj["desc"] as? JsonObject ?: return
                runCatching { json.decodeFromString(Descriptor.serializer(), desc.toString()) }
                    .onSuccess { _incoming.tryEmit(it) }
                    .onFailure { Log.w(TAG, "push invalido: ${it.message}") }
            }
            else -> Log.d(TAG, "Recebido sem _ctrl conhecido: ${t.take(80)}")
        }
    }

    private fun helloLine(): String =
        """{"_ctrl":"hello","device":"$deviceId","name":"${deviceName.replace("\"", "")}"}"""

    private suspend fun configAtual(): PcConfig? = withContext(Dispatchers.IO) {
        val ctx = appContext ?: return@withContext null
        runCatching { Settings(ctx).current() }.getOrNull()
    }

    /** Igual ao SshHandoffTransport: .exe roda direto; senao `python "<script>"`. */
    private fun remoteCmd(agentPath: String, arg: String): String =
        if (agentPath.trim().endsWith(".exe", ignoreCase = true)) {
            "\"${agentPath.trim()}\" $arg"
        } else {
            "python \"$agentPath\" $arg"
        }
}

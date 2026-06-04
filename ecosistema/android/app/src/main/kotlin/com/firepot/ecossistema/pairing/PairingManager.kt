package com.firepot.ecossistema.pairing

import android.content.Context
import android.os.Build
import android.util.Log
import com.firepot.ecossistema.crypto.KeyManager
import com.firepot.ecossistema.data.Settings
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.charset.StandardCharsets

/**
 * Emparelhamento por QR (proposta B), lado Android.
 *
 * 1. Le o QR mostrado pelo PC: {v, host, tshost, port, user, fp, token, pair_port}.
 * 2. Garante o par de chaves local (KeyManager) e pega a publica.
 * 3. Conecta no canal de pareamento (host:pair_port), manda {token, pubkey, ...}.
 * 4. Se o PC autorizar a chave, salva host/user/porta + fingerprint (pinning).
 *
 * Elimina digitar IP/porta e COLAR a chave PEM, e fixa a host key (mata o
 * PromiscuousVerifier). O canal de pareamento e em texto puro, mas e efemero,
 * protegido por token de uso unico e restrito a LAN.
 */
object PairingManager {

    private const val TAG = "PairingManager"
    private val json = Json { ignoreUnknownKeys = true }

    data class QrInfo(
        val host: String,
        val tshost: String?,
        val port: Int,
        val user: String,
        val fingerprint: String,
        val token: String,
        val pairPort: Int,
    )

    /** Tenta interpretar o conteudo do QR. Retorna null se nao for do Ecossistema. */
    fun parse(conteudo: String): QrInfo? {
        val obj: JsonObject = runCatching { json.parseToJsonElement(conteudo.trim()).jsonObject }
            .getOrNull() ?: return null
        fun str(k: String): String? = runCatching { obj[k]?.jsonPrimitive?.content }.getOrNull()
        fun int(k: String, padrao: Int): Int = str(k)?.toIntOrNull() ?: padrao
        val host = str("host") ?: str("tshost") ?: return null
        val token = str("token") ?: return null
        val fp = str("fp") ?: ""
        return QrInfo(
            host = host,
            tshost = str("tshost"),
            port = int("port", 22),
            user = str("user") ?: "",
            fingerprint = fp,
            token = token,
            pairPort = int("pair_port", 8766),
        )
    }

    /** Executa o handshake de pareamento e, em caso de sucesso, salva a config. */
    suspend fun pair(context: Context, info: QrInfo): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val pubLine = KeyManager.ensureKeyPair(context)
            val payload = buildJsonObject {
                put("token", kotlinx.serialization.json.JsonPrimitive(info.token))
                put("pubkey", kotlinx.serialization.json.JsonPrimitive(pubLine))
                put("name", kotlinx.serialization.json.JsonPrimitive(Build.MODEL ?: "Android"))
                put("device", kotlinx.serialization.json.JsonPrimitive(deviceId()))
            }.toString()

            Socket().use { sock ->
                sock.connect(InetSocketAddress(info.host, info.pairPort), 8000)
                sock.soTimeout = 10000
                sock.getOutputStream().apply {
                    write((payload + "\n").toByteArray(StandardCharsets.UTF_8))
                    flush()
                }
                val resp = BufferedReader(
                    InputStreamReader(sock.getInputStream(), StandardCharsets.UTF_8),
                ).readLine() ?: return@withContext Result.failure(
                    IllegalStateException("PC nao respondeu ao pareamento."),
                )
                val ok = runCatching {
                    json.parseToJsonElement(resp).jsonObject["ok"]?.jsonPrimitive?.content
                }.getOrNull() == "true"
                if (!ok) {
                    val erro = runCatching {
                        json.parseToJsonElement(resp).jsonObject["erro"]?.jsonPrimitive?.content
                    }.getOrNull() ?: "recusado"
                    return@withContext Result.failure(IllegalStateException("Pareamento: $erro"))
                }
            }

            Settings(context).savePairing(
                host = info.host,
                user = info.user,
                port = info.port,
                fingerprint = info.fingerprint,
            )
            Log.i(TAG, "Pareado com ${info.host} (user=${info.user})")
            Result.success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Falha no pareamento", e)
            Result.failure(e)
        }
    }

    /** Mesmo id usado pelo PersistentChannel (presenca consistente no PC). */
    private fun deviceId(): String =
        "${Build.MANUFACTURER}-${Build.MODEL}".replace(Regex("[^A-Za-z0-9_-]"), "_")
}

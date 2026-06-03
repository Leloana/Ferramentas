package com.firepot.ecossistema.handoff

import android.content.Context
import android.util.Log
import android.widget.Toast
import com.firepot.ecossistema.data.Settings
import com.firepot.ecossistema.model.Descriptor
import com.firepot.ecossistema.net.HandoffTransport
import com.firepot.ecossistema.net.SshHandoffTransport
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Orquestra um handoff: classifica o conteudo, monta o [Descriptor] e o envia
 * pelo [HandoffTransport]. Da feedback (toast) nos dois extremos — aqui no
 * Android; o agente.py mostra toast no Windows.
 */
object HandoffManager {

    private const val TAG = "HandoffManager"
    private val transport: HandoffTransport = SshHandoffTransport()

    /** Classifica um texto compartilhado (link vs. texto) e monta o descritor. */
    fun fromSharedText(text: String, appOrigem: String = "android.share"): Descriptor {
        val t = text.trim()
        return when {
            isYouTube(t) -> Descriptor.midia(t, posSegundos = youTubeStartSeconds(t), appOrigem = appOrigem)
            isHttpUrl(t) -> Descriptor.url(t, appOrigem)
            else -> Descriptor.texto(t, appOrigem)
        }
    }

    suspend fun send(context: Context, descriptor: Descriptor): Result<Unit> {
        val config = Settings(context).current()
        val result = transport.send(descriptor, config)
        withContext(Dispatchers.Main) {
            val msg = if (result.isSuccess) {
                "Enviado ao PC (${descriptor.tipo})"
            } else {
                "Falha: ${result.exceptionOrNull()?.message ?: "erro"}"
            }
            Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
        }
        if (result.isFailure) Log.e(TAG, "Handoff falhou", result.exceptionOrNull())
        return result
    }

    // ---- Classificadores (espelham a logica do termux-url-opener) ----
    private fun isHttpUrl(s: String): Boolean =
        s.startsWith("http://") || s.startsWith("https://")

    private fun isYouTube(s: String): Boolean =
        s.contains("youtube.com/") || s.contains("youtu.be/")

    /** Extrai `t=` / `start=` (segundos) da URL do YouTube, se houver. */
    private fun youTubeStartSeconds(url: String): Int? {
        val regex = Regex("""[?&](?:t|start)=(\d+)""")
        return regex.find(url)?.groupValues?.get(1)?.toIntOrNull()
    }
}

package com.firepot.ecossistema.handoff

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import android.util.Log
import android.widget.Toast
import com.firepot.ecossistema.data.Settings
import com.firepot.ecossistema.model.Descriptor
import com.firepot.ecossistema.net.HandoffTransport
import com.firepot.ecossistema.net.SshHandoffTransport
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

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

    /** Testa conexão+auth com o PC (sem enviar handoff). Para o indicador de status. */
    suspend fun checkConnection(context: Context): Result<Unit> {
        val config = Settings(context).current()
        return transport.check(config)
    }

    /** Lista os apps do PC (para o usuário escolher ao criar uma ferramenta). */
    suspend fun listApps(context: Context): Result<List<com.firepot.ecossistema.model.PcApp>> {
        val config = Settings(context).current()
        return transport.listApps(config)
    }

    /**
     * Envia um arquivo (content:// Uri) para o PC via SFTP e o revela no Explorer.
     * Copia para um arquivo temporário (necessário p/ ler o stream do provider).
     */
    suspend fun sendFile(context: Context, uri: Uri): Result<Unit> = withContext(Dispatchers.IO) {
        val config = Settings(context).current()
        val name = queryDisplayName(context, uri)
        val temp = File.createTempFile("handoff_", "_$name", context.cacheDir)
        try {
            context.contentResolver.openInputStream(uri)?.use { input ->
                temp.outputStream().use { input.copyTo(it) }
            } ?: run {
                toastMain(context, "Não consegui ler o arquivo.")
                return@withContext Result.failure(IllegalStateException("stream nulo"))
            }
            val up = transport.uploadFile(config, temp.absolutePath, name)
            up.fold(
                onSuccess = { rel ->
                    transport.send(Descriptor.revelar(rel), config) // mostra no PC
                    toastMain(context, "Arquivo enviado ao PC: $name")
                    Result.success(Unit)
                },
                onFailure = {
                    toastMain(context, "Falha ao enviar arquivo: ${it.message ?: "erro"}")
                    Result.failure(it)
                },
            )
        } catch (e: Exception) {
            Log.e(TAG, "sendFile falhou", e)
            toastMain(context, "Falha ao enviar arquivo: ${e.message ?: "erro"}")
            Result.failure(e)
        } finally {
            runCatching { temp.delete() }
        }
    }

    private fun queryDisplayName(context: Context, uri: Uri): String {
        runCatching {
            context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                ?.use { c ->
                    val i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (i >= 0 && c.moveToFirst()) return c.getString(i)
                }
        }
        return uri.lastPathSegment?.substringAfterLast('/') ?: "arquivo"
    }

    private suspend fun toastMain(context: Context, msg: String) = withContext(Dispatchers.Main) {
        Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
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

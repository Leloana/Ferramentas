package app.despertador

import android.content.Context
import android.media.MediaMetadataRetriever
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.time.OffsetDateTime

/** Uma edição já baixada e validada, guardada no armazenamento privado do app. */
class Edicao(val pasta: File, val json: JSONObject) {
    val id: String get() = json.getString("edition_id")
    val dataEditorial: String get() = json.optString("editorial_date")
    val expiraEm: OffsetDateTime? get() = runCatching { OffsetDateTime.parse(json.getString("expires_at")) }.getOrNull()
    val vencida: Boolean get() = expiraEm?.isBefore(OffsetDateTime.now()) ?: true

    fun arquivo(papel: String): File? {
        val assets = json.getJSONArray("assets")
        for (i in 0 until assets.length()) {
            val a = assets.getJSONObject(i)
            if (a.getString("role") == papel) return File(pasta, a.getString("id") + ".mp3").takeIf { it.isFile }
        }
        return null
    }
}

object Edicoes {
    private val ID = Regex("""^\d{4}-\d{2}-\d{2}-r\d+$""")
    private const val MAX_BYTES = 60L * 1024 * 1024
    private const val MAX_MANIFESTO = 512 * 1024

    private fun raiz(ctx: Context) = File(ctx.filesDir, "edicoes").apply { mkdirs() }
    private fun ponteiro(ctx: Context) = File(raiz(ctx), "atual.txt")

    fun atual(ctx: Context): Edicao? = runCatching {
        val id = ponteiro(ctx).readText().trim()
        val pasta = File(raiz(ctx), id)
        Edicao(pasta, JSONObject(File(pasta, "manifest.json").readText()))
    }.getOrNull()

    /** Baixa a edição mais recente. Qualquer falha mantém a edição atual intacta. */
    fun sincronizar(ctx: Context): String {
        val p = Prefs(ctx)
        val msg = try {
            sincronizarOuFalhar(ctx, p)
        } catch (e: Exception) {
            "Falhou: ${e.message ?: e.javaClass.simpleName}"
        }
        if (!msg.startsWith("Falhou")) p.ultimaSync = System.currentTimeMillis()
        p.statusSync = msg
        return msg
    }

    private fun sincronizarOuFalhar(ctx: Context, p: Prefs): String {
        if (p.servidor.isBlank() || p.token.isBlank()) return "Falhou: configure servidor e token"
        val manifesto = JSONObject(String(baixar(p, "/v1/editions/latest", MAX_MANIFESTO.toLong()), Charsets.UTF_8))
        if (manifesto.optInt("schema_version") != 1) throw IOException("versão de manifesto não suportada")
        val id = manifesto.getString("edition_id")
        if (!ID.matches(id)) throw IOException("id de edição inválido")
        if (atual(ctx)?.id == id) return "Já está com a edição $id"

        val assets = manifesto.getJSONArray("assets")
        if (assets.length() !in 1..4) throw IOException("número de arquivos inesperado")
        val tmp = File(raiz(ctx), ".tmp-$id")
        tmp.deleteRecursively(); tmp.mkdirs()
        try {
            for (i in 0 until assets.length()) {
                val a = assets.getJSONObject(i)
                val assetId = a.getString("id")
                val caminho = a.getString("path")
                val bytes = a.getLong("bytes")
                if (!assetId.startsWith("$id-") || !caminho.startsWith("/v1/assets/") || caminho.contains(".."))
                    throw IOException("arquivo com caminho inválido")
                if (bytes <= 0 || bytes > MAX_BYTES) throw IOException("arquivo grande demais")
                val dados = baixar(p, caminho, bytes)
                if (dados.size.toLong() != bytes) throw IOException("download incompleto de $assetId")
                if (sha256(dados) != a.getString("sha256").lowercase()) throw IOException("hash não confere em $assetId")
                val f = File(tmp, "$assetId.mp3")
                f.writeBytes(dados)
                if (!tocavel(f)) throw IOException("$assetId não é um áudio válido")
            }
            File(tmp, "manifest.json").writeText(manifesto.toString())
            val destino = File(raiz(ctx), id)
            destino.deleteRecursively()
            if (!tmp.renameTo(destino)) throw IOException("não consegui promover a edição")
            val pt = File(raiz(ctx), "atual.tmp")
            pt.writeText(id)
            if (!pt.renameTo(ponteiro(ctx))) throw IOException("não consegui trocar a edição atual")
        } finally {
            tmp.deleteRecursively()
        }
        limpar(ctx, manter = id)
        return "Baixada a edição $id"
    }

    /** Mantém a edição atual e a anterior; apaga o resto. */
    private fun limpar(ctx: Context, manter: String) {
        val pastas = raiz(ctx).listFiles { f -> f.isDirectory && ID.matches(f.name) }?.sortedByDescending { it.name } ?: return
        val anterior = pastas.firstOrNull { it.name != manter }?.name
        pastas.filter { it.name != manter && it.name != anterior }.forEach { it.deleteRecursively() }
    }

    private fun baixar(p: Prefs, caminho: String, limite: Long): ByteArray {
        val url = URL(p.servidor + caminho)
        if (url.protocol != "http" && url.protocol != "https") throw IOException("endereço inválido")
        val c = url.openConnection() as HttpURLConnection
        try {
            c.instanceFollowRedirects = false  // o token nunca vai para outro endereço
            c.connectTimeout = 8_000
            c.readTimeout = 30_000
            c.setRequestProperty("Authorization", "Bearer ${p.token}")
            when (val code = c.responseCode) {
                200 -> {}
                401 -> throw IOException("token recusado pelo servidor")
                404 -> throw IOException("servidor sem edição publicada")
                else -> throw IOException("servidor respondeu $code")
            }
            c.inputStream.use { ins ->
                val out = java.io.ByteArrayOutputStream()
                val buf = ByteArray(64 * 1024)
                while (true) {
                    val n = ins.read(buf)
                    if (n < 0) break
                    out.write(buf, 0, n)
                    if (out.size() > limite) throw IOException("resposta maior que o esperado")
                }
                return out.toByteArray()
            }
        } finally {
            c.disconnect()
        }
    }

    private fun sha256(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

    private fun tocavel(f: File): Boolean = runCatching {
        val r = MediaMetadataRetriever()
        try {
            r.setDataSource(f.absolutePath)
            (r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L) > 1000
        } finally {
            r.release()
        }
    }.getOrDefault(false)
}

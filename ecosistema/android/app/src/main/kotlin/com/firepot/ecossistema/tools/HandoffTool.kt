package com.firepot.ecossistema.tools

import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import com.firepot.ecossistema.handoff.HandoffManager
import com.firepot.ecossistema.model.Descriptor
import com.firepot.ecossistema.service.HandoffAccessibilityService

/**
 * Catálogo de ferramentas do overlay. Cada ferramenta vira um botão (só o ícone)
 * na bolha flutuante e uma linha (ícone + texto + explicação + toggle) na aba
 * "Ferramentas" do app. O usuário liga/desliga o que achar útil.
 *
 * @param icon emoji usado como ícone (no overlay aparece só ele).
 */
data class HandoffTool(
    val id: String,
    val icon: String,
    val title: String,
    val description: String,
    val howItWorks: String,
) {
    companion object {
        val ALL: List<HandoffTool> = listOf(
            HandoffTool(
                id = "link",
                icon = "🔗",
                title = "Link da tela",
                description = "Manda a página aberta no navegador para abrir no PC.",
                howItWorks = "Lê a URL da barra de endereço via Acessibilidade. " +
                    "Funciona melhor no Samsung Internet; o Chrome recente costuma " +
                    "esconder a URL — nesse caso use Compartilhar → Ecossistema. " +
                    "Links do YouTube vão com o tempo (t=).",
            ),
            HandoffTool(
                id = "clipboard",
                icon = "📋",
                title = "Texto copiado",
                description = "Cola no PC o texto que você copiou no celular.",
                howItWorks = "Lê o clipboard do Android e envia como texto para o " +
                    "clipboard do PC. No Android 10+ a leitura em segundo plano pode " +
                    "vir vazia; nesse caso o app avisa.",
            ),
            HandoffTool(
                id = "mapa",
                icon = "🗺️",
                title = "Endereço copiado no Mapa",
                description = "Abre no Google Maps do PC o endereço/coordenada copiado.",
                howItWorks = "Usa o texto do clipboard como busca no Google Maps do PC.",
            ),
            HandoffTool(
                id = "downloads",
                icon = "📁",
                title = "Abrir Downloads no PC",
                description = "Abre a pasta Downloads no Explorer do PC.",
                howItWorks = "Envia um atalho de pasta fixo; o agente do PC mapeia " +
                    "para a pasta local correspondente.",
            ),
            HandoffTool(
                id = "file",
                icon = "📎",
                title = "Enviar arquivo",
                description = "Escolhe um arquivo no celular; ele vai pra pasta Ecossistema do PC e abre.",
                howItWorks = "Abre o seletor de arquivos; sobe o arquivo por SFTP para a " +
                    "pasta \"Ecossistema\" no PC e o abre no app padrão. Dica: também dá " +
                    "pra Compartilhar qualquer arquivo → Ecossistema.",
            ),
            HandoffTool(
                id = "test",
                icon = "🧪",
                title = "Testar conexão",
                description = "Abre example.com no PC — útil para checar se está tudo certo.",
                howItWorks = "Envia uma URL fixa de teste para o PC abrir no navegador.",
            ),
        )

        val DEFAULT_ENABLED: Set<String> = ALL.map { it.id }.toSet()

        fun byId(id: String): HandoffTool? = ALL.firstOrNull { it.id == id }
    }
}

/** Monta o descritor de uma ferramenta (ou mostra um toast com o motivo e devolve null). */
object ToolRunner {

    fun buildDescriptor(context: Context, toolId: String): Descriptor? = when (toolId) {
        "link" -> {
            val url = HandoffAccessibilityService.lastUrl
            if (url.isNullOrBlank()) {
                // O Chrome recente costuma nao expor a URL pela Acessibilidade.
                // Orienta o caminho robusto: Compartilhar -> Ecossistema.
                toast(context, "Não consegui ler a URL (o Chrome esconde). Use Compartilhar → Ecossistema.")
                null
            } else {
                HandoffManager.fromSharedText(url)
            }
        }
        "clipboard" -> {
            val t = clipboardText(context)
            if (t.isBlank()) {
                toast(context, "Clipboard vazio ou sem acesso em segundo plano (Android 10+).")
                null
            } else {
                Descriptor.texto(t)
            }
        }
        "mapa" -> {
            val t = clipboardText(context)
            if (t.isBlank()) {
                toast(context, "Copie um endereço primeiro — o clipboard está vazio.")
                null
            } else {
                Descriptor.mapa(t)
            }
        }
        "downloads" -> Descriptor.pasta("/storage/emulated/0/Download/")
        "test" -> Descriptor.url("https://example.com")
        else -> null
    }

    private fun clipboardText(context: Context): String {
        val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = cm.primaryClip
        return if (clip != null && clip.itemCount > 0) {
            clip.getItemAt(0).coerceToText(context).toString().trim()
        } else {
            ""
        }
    }

    private fun toast(context: Context, msg: String) =
        Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
}

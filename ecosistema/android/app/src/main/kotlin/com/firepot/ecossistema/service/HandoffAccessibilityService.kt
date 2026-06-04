package com.firepot.ecossistema.service

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Le, com permissao do usuario, o app/URL em foco para que o gesto
 * "arrastar pro canto" leve o ESTADO (e nao so um link generico).
 *
 * Marco 1: captura o pacote em foco e, para navegadores conhecidos, tenta ler
 * a barra de endereco (URL). YouTube/Chrome cobrem os casos do criterio de
 * pronto. Estado mais rico (timestamp exato do player) e evolucao futura.
 */
class HandoffAccessibilityService : AccessibilityService() {

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event ?: return
        val pkg = event.packageName?.toString() ?: return
        if (pkg == packageName) return // ignora a propria UI/overlay
        lastForegroundPackage = pkg

        // Tenta extrair URL da barra de endereco de navegadores comuns.
        val urlNodeIds = BROWSER_URL_BAR_IDS[pkg] ?: return
        val root: AccessibilityNodeInfo = rootInActiveWindow ?: return
        try {
            for (urlNodeId in urlNodeIds) {
                val nodes = root.findAccessibilityNodeInfosByViewId(urlNodeId)
                // O Chrome recente costuma esconder o texto da omnibox; quando isso
                // acontece o `text` vem vazio mas o `contentDescription` pode trazer
                // a URL/dominio. Tenta os dois antes de desistir.
                val node = nodes?.firstOrNull() ?: continue
                val bruto = node.text?.toString()?.takeIf { it.isNotBlank() }
                    ?: node.contentDescription?.toString()?.takeIf { it.isNotBlank() }
                if (bruto != null && pareceUrl(bruto)) {
                    lastUrl = normalizeUrl(bruto)
                    return
                }
            }
        } catch (_: Exception) {
            // best-effort: ignora falhas de leitura
        }
    }

    /** Heuristica simples: tem ponto e nao tem espaco (descarta titulo/busca). */
    private fun pareceUrl(s: String): Boolean {
        val t = s.trim()
        if (t.isEmpty() || t.contains(' ')) return false
        return t.startsWith("http://") || t.startsWith("https://") || t.contains('.')
    }

    override fun onInterrupt() { /* nada a fazer */ }

    private fun normalizeUrl(raw: String): String {
        val s = raw.trim()
        return if (s.startsWith("http://") || s.startsWith("https://")) s else "https://$s"
    }

    companion object {
        /** Ultimo pacote/URL em foco — lido pelo overlay ao disparar o handoff. */
        @Volatile var lastForegroundPackage: String? = null
            private set

        @Volatile var lastUrl: String? = null
            private set

        /** ids da barra de endereco por navegador (resource-id do view). Mais de
         *  um por pacote porque variam entre versoes/variantes do mesmo browser. */
        private val BROWSER_URL_BAR_IDS = mapOf(
            "com.android.chrome" to listOf(
                "com.android.chrome:id/url_bar",
                "com.android.chrome:id/location_bar_status",
            ),
            "com.chrome.beta" to listOf("com.chrome.beta:id/url_bar"),
            "com.sec.android.app.sbrowser" to listOf(
                "com.sec.android.app.sbrowser:id/location_bar_edit_text",
                "com.sec.android.app.sbrowser:id/sbrowser_url_bar",
            ),
            "org.mozilla.firefox" to listOf("org.mozilla.firefox:id/mozac_browser_toolbar_url_view"),
        )
    }
}

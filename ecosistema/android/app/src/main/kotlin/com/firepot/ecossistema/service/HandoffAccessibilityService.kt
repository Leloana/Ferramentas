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
        val urlNodeId = BROWSER_URL_BAR_IDS[pkg] ?: return
        val root: AccessibilityNodeInfo = rootInActiveWindow ?: return
        try {
            val nodes = root.findAccessibilityNodeInfosByViewId(urlNodeId)
            val url = nodes?.firstOrNull()?.text?.toString()
            if (!url.isNullOrBlank()) {
                lastUrl = normalizeUrl(url)
            }
        } catch (_: Exception) {
            // best-effort: ignora falhas de leitura
        }
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

        /** id da barra de endereco por navegador (resource-id do view). */
        private val BROWSER_URL_BAR_IDS = mapOf(
            "com.android.chrome" to "com.android.chrome:id/url_bar",
            "com.sec.android.app.sbrowser" to
                "com.sec.android.app.sbrowser:id/location_bar_edit_text",
        )
    }
}

package com.firepot.ecossistema.share

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import com.firepot.ecossistema.handoff.HandoffManager
import kotlinx.coroutines.launch

/**
 * Share target: "Compartilhar -> Ecossistema". Recebe link/texto **ou
 * arquivo(s)** de qualquer app e manda pro PC (texto/link viram descritor;
 * arquivos sobem por SFTP). Sem UI (activity translúcida).
 */
class ShareReceiverActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val files = collectStreamUris(intent)
        if (files.isNotEmpty()) {
            lifecycleScope.launch {
                for (uri in files) HandoffManager.sendFile(applicationContext, uri)
                finish()
            }
            return
        }

        val shared = if (intent?.action == Intent.ACTION_SEND) {
            intent.getStringExtra(Intent.EXTRA_TEXT)
        } else {
            null
        }
        if (shared.isNullOrBlank()) {
            finish()
            return
        }
        val descriptor = HandoffManager.fromSharedText(shared)
        lifecycleScope.launch {
            HandoffManager.send(applicationContext, descriptor)
            finish()
        }
    }

    @Suppress("DEPRECATION")
    private fun collectStreamUris(intent: Intent?): List<Uri> {
        intent ?: return emptyList()
        return when (intent.action) {
            Intent.ACTION_SEND -> {
                val u = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
                } else {
                    intent.getParcelableExtra(Intent.EXTRA_STREAM)
                }
                listOfNotNull(u)
            }
            Intent.ACTION_SEND_MULTIPLE -> {
                val list = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
                } else {
                    intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM)
                }
                list ?: emptyList()
            }
            else -> emptyList()
        }
    }
}

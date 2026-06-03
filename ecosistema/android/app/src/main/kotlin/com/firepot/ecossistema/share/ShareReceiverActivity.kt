package com.firepot.ecossistema.share

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import com.firepot.ecossistema.handoff.HandoffManager
import kotlinx.coroutines.launch

/**
 * Share target: "Compartilhar -> Ecossistema". Recebe um link/texto de
 * qualquer app, monta o descritor e envia ao PC. Sem UI (activity translucida).
 */
class ShareReceiverActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
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
}

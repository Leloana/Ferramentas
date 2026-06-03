package com.firepot.ecossistema.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Religa o Foreground Service (e o overlay) depois que o celular reinicia,
 * para a bolha de atalhos voltar sozinha sem o usuário abrir o app.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action == Intent.ACTION_BOOT_COMPLETED) {
            // Em alguns Android iniciar FGS no boot pode ser restrito; nao quebra se falhar.
            runCatching { HandoffForegroundService.start(context) }
                .onFailure { Log.w("BootReceiver", "Nao consegui subir o serviço no boot", it) }
        }
    }
}

package com.firepot.ecossistema.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import com.firepot.ecossistema.R
import com.firepot.ecossistema.overlay.CornerOverlayService

/**
 * Servico em foreground: mantem o app vivo (canal + gestos) mesmo com
 * otimizacoes de bateria do fabricante (Samsung), e sobe o overlay
 * "arrastar pro canto" enquanto ativo.
 */
class HandoffForegroundService : Service() {

    override fun onCreate() {
        super.onCreate()
        startAsForeground()
        isRunning = true
        // Inicia o overlay junto (depende de SYSTEM_ALERT_WINDOW concedido).
        startService(Intent(this, CornerOverlayService::class.java))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        isRunning = false
        stopService(Intent(this, CornerOverlayService::class.java))
        super.onDestroy()
    }

    private fun startAsForeground() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.channel_handoff),
                NotificationManager.IMPORTANCE_LOW,
            )
            nm.createNotificationChannel(channel)
        }
        val notification: Notification = Notification.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.fg_running))
            .setContentText(getString(R.string.fg_desc))
            .setSmallIcon(R.drawable.ic_launcher)
            .setOngoing(true)
            .build()
        startForeground(NOTIF_ID, notification)
    }

    companion object {
        /** Estado do serviço (para o toggle do app refletir ligado/desligado). */
        @Volatile var isRunning: Boolean = false
            private set

        private const val CHANNEL_ID = "handoff_fg"
        private const val NOTIF_ID = 1001

        fun start(context: Context) {
            val intent = Intent(context, HandoffForegroundService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, HandoffForegroundService::class.java))
        }
    }
}

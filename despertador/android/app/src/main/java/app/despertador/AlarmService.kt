package app.despertador

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Toca a sequência do despertador só com arquivos locais:
 *   toque embarcado (volume crescente) -> jornal (ou aviso, se faltar/vencer) -> música -> toque em loop.
 * Qualquer arquivo que falhe é pulado; no fim sempre sobra o toque embarcado, até Parar/Soneca
 * ou o limite de duração.
 */
class AlarmService : Service() {

    private sealed class Item {
        data class Bruto(val res: Int, val rampa: Boolean = false) : Item()
        data class Arquivo(val f: File) : Item()
    }

    private val handler = Handler(Looper.getMainLooper())
    private var player: MediaPlayer? = null
    private var fila = ArrayDeque<Item>()
    private var wake: PowerManager.WakeLock? = null
    private var foco: AudioFocusRequest? = null
    private var resumo = ""

    private val attrs = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_ALARM)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
        .build()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACAO_PARAR -> { encerrar(); return START_NOT_STICKY }
            ACAO_SONECA -> {
                Agendador.agendarPontual(this, SONECA_MS)
                encerrar()
                return START_NOT_STICKY
            }
        }
        startForeground(NOTIF_ID, notificacao(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
        comecar()
        return START_NOT_STICKY
    }

    private fun comecar() {
        liberarPlayer()
        handler.removeCallbacksAndMessages(null)
        if (wake == null) {
            wake = getSystemService(PowerManager::class.java)
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "despertador:tocar")
                .apply { acquire(LIMITE_MS + 60_000) }
        }
        val am = getSystemService(AudioManager::class.java)
        foco = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT).setAudioAttributes(attrs).build()
            .also { am.requestAudioFocus(it) }

        fila = ArrayDeque(montarSequencia())
        handler.postDelayed({ encerrar() }, LIMITE_MS)
        val hora = SimpleDateFormat("dd/MM HH:mm", Locale("pt", "BR")).format(Date())
        Prefs(this).ultimoToque = "$hora — $resumo"
        proximo()
    }

    private fun montarSequencia(): List<Item> {
        val itens = mutableListOf<Item>(Item.Bruto(R.raw.toque, rampa = true))
        val ed = Edicoes.atual(this)
        val narracao = ed?.takeUnless { it.vencida }?.arquivo("narration")
        val partes = mutableListOf<String>()
        if (ed != null && narracao != null) {
            itens += Item.Arquivo(narracao); partes += "jornal ${ed.id}"
        } else {
            itens += Item.Bruto(R.raw.aviso)
            partes += if (ed == null) "sem jornal baixado (aviso)" else "jornal ${ed.id} vencido (aviso)"
        }
        ed?.arquivo("music")?.let { itens += Item.Arquivo(it); partes += "música" }
        resumo = partes.joinToString(" + ")
        return itens
    }

    private fun proximo() {
        liberarPlayer()
        val item = fila.removeFirstOrNull()
        if (item == null) { tocarReservaEmLoop(); return }
        try {
            val mp = MediaPlayer()
            mp.setAudioAttributes(attrs)
            mp.setWakeMode(this, PowerManager.PARTIAL_WAKE_LOCK)
            when (item) {
                is Item.Bruto -> resources.openRawResourceFd(item.res).use {
                    mp.setDataSource(it.fileDescriptor, it.startOffset, it.length)
                }
                is Item.Arquivo -> mp.setDataSource(item.f.absolutePath)
            }
            mp.setOnCompletionListener { proximo() }
            mp.setOnErrorListener { _, _, _ -> handler.post { proximo() }; true }
            mp.prepare()
            player = mp
            if (item is Item.Bruto && item.rampa) rampa(mp) else mp.setVolume(1f, 1f)
            mp.start()
        } catch (e: Exception) {
            // Arquivo corrompido/ausente: segue para o próximo (no fim, o toque embarcado).
            handler.post { proximo() }
        }
    }

    private fun tocarReservaEmLoop() {
        try {
            val mp = MediaPlayer.create(this, R.raw.toque, attrs, getSystemService(AudioManager::class.java).generateAudioSessionId())
                ?: run { encerrar(); return }
            mp.setWakeMode(this, PowerManager.PARTIAL_WAKE_LOCK)
            mp.isLooping = true
            player = mp
            mp.start()
        } catch (e: Exception) {
            encerrar()
        }
    }

    private fun rampa(mp: MediaPlayer) {
        val passos = 16
        for (i in 0..passos) {
            handler.postDelayed({
                if (player === mp) {
                    val v = 0.15f + 0.85f * i / passos
                    runCatching { mp.setVolume(v, v) }
                }
            }, i * 500L)
        }
    }

    private fun liberarPlayer() {
        player?.let { runCatching { it.stop() }; it.release() }
        player = null
    }

    private fun encerrar() {
        handler.removeCallbacksAndMessages(null)
        liberarPlayer()
        foco?.let { getSystemService(AudioManager::class.java).abandonAudioFocusRequest(it) }
        foco = null
        wake?.let { if (it.isHeld) it.release() }
        wake = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        liberarPlayer()
        wake?.let { if (it.isHeld) it.release() }
        super.onDestroy()
    }

    private fun notificacao(): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CANAL) == null) {
            nm.createNotificationChannel(NotificationChannel(CANAL, "Alarme tocando", NotificationManager.IMPORTANCE_HIGH).apply {
                setSound(null, null)  // o som é tocado pelo próprio serviço
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            })
        }
        fun acao(acao: String, cod: Int) = PendingIntent.getService(
            this, cod, Intent(this, AlarmService::class.java).setAction(acao),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val abrir = PendingIntent.getActivity(
            this, 2, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return Notification.Builder(this, CANAL)
            .setSmallIcon(R.drawable.ic_alarme)
            .setContentTitle("Bom dia!")
            .setContentText("Despertador tocando")
            .setCategory(Notification.CATEGORY_ALARM)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setOngoing(true)
            .setContentIntent(abrir)
            .addAction(Notification.Action.Builder(null, "Parar", acao(ACAO_PARAR, 10)).build())
            .addAction(Notification.Action.Builder(null, "Soneca 9 min", acao(ACAO_SONECA, 11)).build())
            .build()
    }

    companion object {
        const val ACAO_TOCAR = "app.despertador.TOCAR"
        const val ACAO_PARAR = "app.despertador.PARAR"
        const val ACAO_SONECA = "app.despertador.SONECA"
        private const val CANAL = "alarme"
        private const val NOTIF_ID = 7
        const val SONECA_MS = 9 * 60 * 1000L
        private const val LIMITE_MS = 15 * 60 * 1000L
    }
}

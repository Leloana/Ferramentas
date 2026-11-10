package app.despertador

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import java.time.ZonedDateTime

/**
 * Mantém sempre UM alarme no AlarmManager (setAlarmClock): o mais próximo entre o
 * recorrente (hora + dias) e o pontual (soneca/teste). Recalculado a cada disparo,
 * boot, troca de horário/fuso e mudança de configuração.
 */
object Agendador {

    fun proximoRecorrente(p: Prefs, agora: ZonedDateTime = ZonedDateTime.now()): ZonedDateTime? {
        if (!p.ativo || p.dias.isEmpty()) return null
        var c = agora.withHour(p.hora).withMinute(p.minuto).withSecond(0).withNano(0)
        if (!c.isAfter(agora)) c = c.plusDays(1)
        repeat(8) {
            if (c.dayOfWeek.value in p.dias) return c
            c = c.plusDays(1)
        }
        return null
    }

    /** Epoch ms do próximo disparo, ou null se não houver nada agendado. */
    fun proximo(ctx: Context): Long? {
        val p = Prefs(ctx)
        val agora = System.currentTimeMillis()
        val pontual = p.pontual.takeIf { it > agora }
        if (pontual == null && p.pontual != 0L) p.pontual = 0L
        val recorrente = proximoRecorrente(p)?.toInstant()?.toEpochMilli()
        return listOfNotNull(pontual, recorrente).minOrNull()
    }

    fun podeAgendar(ctx: Context): Boolean =
        ctx.getSystemService(AlarmManager::class.java).canScheduleExactAlarms()

    fun reagendar(ctx: Context) {
        val am = ctx.getSystemService(AlarmManager::class.java)
        val disparo = pendente(ctx)
        am.cancel(disparo)
        val quando = proximo(ctx) ?: return
        if (!am.canScheduleExactAlarms()) return
        val abrir = PendingIntent.getActivity(
            ctx, 1, Intent(ctx, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        am.setAlarmClock(AlarmManager.AlarmClockInfo(quando, abrir), disparo)
    }

    fun agendarPontual(ctx: Context, emMs: Long) {
        Prefs(ctx).pontual = System.currentTimeMillis() + emMs
        reagendar(ctx)
    }

    private fun pendente(ctx: Context): PendingIntent = PendingIntent.getBroadcast(
        ctx, 0, Intent(ctx, AlarmReceiver::class.java),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )
}

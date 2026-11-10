package app.despertador

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Disparo do alarme: começa a tocar e já agenda o próximo. Nada aqui usa rede. */
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val p = Prefs(ctx)
        if (p.pontual != 0L && p.pontual <= System.currentTimeMillis() + 60_000) p.pontual = 0L
        ctx.startForegroundService(Intent(ctx, AlarmService::class.java).setAction(AlarmService.ACAO_TOCAR))
        Agendador.reagendar(ctx)
    }
}

/** Reinício, atualização do app ou troca de horário/fuso: recalcula o alarme e o job de sync. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        Agendador.reagendar(ctx)
        SyncJob.agendar(ctx)
    }
}

package app.despertador

import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context

/** Sincronização oportunista: o sistema roda quando houver rede, sem horário garantido. */
class SyncJob : JobService() {
    override fun onStartJob(params: JobParameters): Boolean {
        Thread {
            Edicoes.sincronizar(this)
            jobFinished(params, false)
        }.start()
        return true
    }

    override fun onStopJob(params: JobParameters) = true

    companion object {
        private const val ID = 42

        /** Nunca deixa uma falha no agendamento da sync derrubar o app ou o boot. */
        fun agendar(ctx: Context) {
            runCatching { agendarOuFalhar(ctx) }
                .onFailure { android.util.Log.w("Despertador", "não agendou a sincronização", it) }
        }

        private fun agendarOuFalhar(ctx: Context) {
            val js = ctx.getSystemService(JobScheduler::class.java)
            if (js.getPendingJob(ID) != null) return
            js.schedule(
                JobInfo.Builder(ID, ComponentName(ctx, SyncJob::class.java))
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_UNMETERED)  // Wi-Fi de casa
                    .setPeriodic(3 * 60 * 60 * 1000L)
                    .setPersisted(true)
                    .build(),
            )
        }
    }
}

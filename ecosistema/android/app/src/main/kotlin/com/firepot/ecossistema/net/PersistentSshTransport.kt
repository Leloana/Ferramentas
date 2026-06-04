package com.firepot.ecossistema.net

import android.util.Log
import com.firepot.ecossistema.data.PcConfig
import com.firepot.ecossistema.model.Descriptor
import com.firepot.ecossistema.model.PcApp

/**
 * Transporte que prioriza o CANAL PERSISTENTE (proposta A): se ele estiver vivo,
 * o envio do descritor e so "escrever uma linha" no canal ja pronto (instantaneo).
 * Se o canal estiver caido, cai automaticamente para o [SshHandoffTransport]
 * (uma sessao SSH por evento, `--send`) — o fallback que ja funcionava.
 *
 * `check`/`listApps`/`uploadFile` continuam pelo SSH por-evento: nao sao
 * sensiveis a latencia (e o SFTP precisa de uma sessao propria de qualquer jeito).
 */
class PersistentSshTransport(
    private val fallback: SshHandoffTransport = SshHandoffTransport(),
) : HandoffTransport {

    override suspend fun send(descriptor: Descriptor, config: PcConfig): Result<Unit> {
        if (!config.isComplete) {
            return Result.failure(IllegalStateException("Configuracao do PC incompleta (host/user/chave)."))
        }
        if (PersistentChannel.isOnline()) {
            // Caminho rapido: o canal ja esta autenticado e aberto.
            PersistentChannel.enqueue(descriptor.toJsonLine())
            Log.i(TAG, "Handoff pelo canal persistente: tipo=${descriptor.tipo}")
            return Result.success(Unit)
        }
        Log.i(TAG, "Canal offline; usando fallback --send (tipo=${descriptor.tipo})")
        return fallback.send(descriptor, config)
    }

    override suspend fun check(config: PcConfig): Result<Unit> =
        fallback.check(config)

    override suspend fun listApps(config: PcConfig): Result<List<PcApp>> =
        fallback.listApps(config)

    override suspend fun uploadFile(
        config: PcConfig,
        localPath: String,
        remoteName: String,
        remoteDir: String,
    ): Result<String> = fallback.uploadFile(config, localPath, remoteName, remoteDir)

    private companion object {
        const val TAG = "PersistentSshTransport"
    }
}

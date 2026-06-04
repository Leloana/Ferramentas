package com.firepot.ecossistema.net

import com.firepot.ecossistema.data.PcConfig
import com.firepot.ecossistema.model.Descriptor
import com.firepot.ecossistema.model.PcApp

/**
 * Abstrai o envio de um descritor ao Agente Windows. Implementacao atual:
 * [SshHandoffTransport]. Fases futuras podem somar um canal TLS dedicado /
 * descoberta NSD na LAN, mantendo a mesma interface.
 */
interface HandoffTransport {
    suspend fun send(descriptor: Descriptor, config: PcConfig): Result<Unit>

    /** Conecta + autentica (sem enviar nada) só para checar se o PC está acessível. */
    suspend fun check(config: PcConfig): Result<Unit>

    /** Lista os apps do PC (via `agente.py --list-apps`). */
    suspend fun listApps(config: PcConfig): Result<List<PcApp>>

    /**
     * Sobe um arquivo para o PC via SFTP. Destino = `<remoteDir>/<remoteName>`
     * relativo ao home do usuário no PC. Retorna esse caminho relativo.
     */
    suspend fun uploadFile(
        config: PcConfig,
        localPath: String,
        remoteName: String,
        remoteDir: String = "Downloads",
    ): Result<String>
}

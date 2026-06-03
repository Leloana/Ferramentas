package com.firepot.ecossistema.net

import android.util.Log
import com.firepot.ecossistema.data.PcConfig
import com.firepot.ecossistema.model.Descriptor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import net.schmizz.sshj.SSHClient
import net.schmizz.sshj.transport.verification.PromiscuousVerifier

/**
 * Entrega o descritor rodando, por SSH, `python "<agentPath>" --send` no PC e
 * escrevendo o JSON na STDIN do comando remoto — exatamente como a ponte
 * Termux (termux-url-opener). O `--send` do agente repassa ao daemon que roda
 * na sessao interativa do usuario (lecao da Sessao 0/1, PLANO.md secao 3).
 *
 * NOTA de seguranca: usamos PromiscuousVerifier (aceita qualquer host key) por
 * praticidade no Marco 1. Em produção, fixar a host key do PC (pinning) ou
 * confiar via Tailscale. TODO: emparelhamento + known_hosts.
 */
class SshHandoffTransport : HandoffTransport {

    override suspend fun send(descriptor: Descriptor, config: PcConfig): Result<Unit> =
        withContext(Dispatchers.IO) {
            if (!config.isComplete) {
                return@withContext Result.failure(
                    IllegalStateException("Configuracao do PC incompleta (host/user/chave)."),
                )
            }
            val ssh = SSHClient()
            try {
                ssh.addHostKeyVerifier(PromiscuousVerifier())
                ssh.connect(config.host, config.port)

                val keys = ssh.loadKeys(config.privateKeyPem, null, null)
                ssh.authPublickey(config.user, keys)

                ssh.startSession().use { session ->
                    // Aspas no path para caminhos do Windows com espacos.
                    val cmd = session.exec("python \"${config.agentPath}\" --send")
                    cmd.outputStream.use { out ->
                        out.write(descriptor.toJsonLine().toByteArray(Charsets.UTF_8))
                        out.write('\n'.code)
                    }
                    cmd.join() // espera o comando terminar
                    val status = cmd.exitStatus
                    if (status != null && status != 0) {
                        return@withContext Result.failure(
                            RuntimeException("Agente retornou codigo $status"),
                        )
                    }
                }
                Log.i(TAG, "Handoff enviado: tipo=${descriptor.tipo}")
                Result.success(Unit)
            } catch (e: Exception) {
                Log.e(TAG, "Falha no handoff SSH", e)
                Result.failure(e)
            } finally {
                runCatching { ssh.disconnect() }
            }
        }

    private companion object {
        const val TAG = "SshHandoff"
    }
}

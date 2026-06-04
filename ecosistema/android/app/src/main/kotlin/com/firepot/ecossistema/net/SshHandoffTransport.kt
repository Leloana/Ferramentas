package com.firepot.ecossistema.net

import android.util.Log
import com.firepot.ecossistema.data.PcConfig
import com.firepot.ecossistema.model.Descriptor
import com.firepot.ecossistema.model.PcApp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import net.schmizz.sshj.SSHClient

/**
 * Entrega o descritor rodando, por SSH, `python "<agentPath>" --send` no PC e
 * escrevendo o JSON na STDIN do comando remoto — exatamente como a ponte
 * Termux (termux-url-opener). O `--send` do agente repassa ao daemon que roda
 * na sessao interativa do usuario (lecao da Sessao 0/1, PLANO.md secao 3).
 *
 * Seguranca: a verificacao da host key vem de [HostKeyVerifiers.forFingerprint]
 * — com fingerprint fixado no pareamento (proposta B) faz PINNING; sem ele
 * (config legada, chave colada) cai no verificador promiscuo de fallback.
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
                ssh.addHostKeyVerifier(HostKeyVerifiers.forFingerprint(config.hostKeyFingerprint))
                ssh.connect(config.host, config.port)

                val keys = ssh.loadKeys(config.privateKeyPem, null, null)
                ssh.authPublickey(config.user, keys)

                ssh.startSession().use { session ->
                    val cmd = session.exec(remoteCmd(config.agentPath, "--send"))
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

    override suspend fun check(config: PcConfig): Result<Unit> =
        withContext(Dispatchers.IO) {
            if (!config.isComplete) {
                return@withContext Result.failure(
                    IllegalStateException("Configuracao do PC incompleta (host/user/chave)."),
                )
            }
            val ssh = SSHClient()
            ssh.connectTimeout = 5000
            ssh.timeout = 5000
            try {
                ssh.addHostKeyVerifier(HostKeyVerifiers.forFingerprint(config.hostKeyFingerprint))
                ssh.connect(config.host, config.port)
                val keys = ssh.loadKeys(config.privateKeyPem, null, null)
                ssh.authPublickey(config.user, keys)
                Result.success(Unit)
            } catch (e: Exception) {
                Result.failure(e)
            } finally {
                runCatching { ssh.disconnect() }
            }
        }

    override suspend fun listApps(config: PcConfig): Result<List<PcApp>> =
        withContext(Dispatchers.IO) {
            if (!config.isComplete) {
                return@withContext Result.failure(
                    IllegalStateException("Configuracao do PC incompleta (host/user/chave)."),
                )
            }
            val ssh = SSHClient()
            ssh.connectTimeout = 8000
            ssh.timeout = 8000
            try {
                ssh.addHostKeyVerifier(HostKeyVerifiers.forFingerprint(config.hostKeyFingerprint))
                ssh.connect(config.host, config.port)
                val keys = ssh.loadKeys(config.privateKeyPem, null, null)
                ssh.authPublickey(config.user, keys)
                ssh.startSession().use { session ->
                    val cmd = session.exec(remoteCmd(config.agentPath, "--list-apps"))
                    val out = cmd.inputStream.readBytes().toString(Charsets.UTF_8)
                    cmd.join()
                    val apps = JSON.decodeFromString<List<PcApp>>(out.trim())
                    Result.success(apps)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Falha ao listar apps do PC", e)
                Result.failure(e)
            } finally {
                runCatching { ssh.disconnect() }
            }
        }

    override suspend fun uploadFile(
        config: PcConfig,
        localPath: String,
        remoteName: String,
        remoteDir: String,
    ): Result<String> = withContext(Dispatchers.IO) {
        if (!config.isComplete) {
            return@withContext Result.failure(
                IllegalStateException("Configuracao do PC incompleta (host/user/chave)."),
            )
        }
        val safeName = remoteName.replace('/', '_').replace('\\', '_')
        val dest = "$remoteDir/$safeName"
        val ssh = SSHClient()
        ssh.connectTimeout = 8000
        try {
            ssh.addHostKeyVerifier(HostKeyVerifiers.forFingerprint(config.hostKeyFingerprint))
            ssh.connect(config.host, config.port)
            val keys = ssh.loadKeys(config.privateKeyPem, null, null)
            ssh.authPublickey(config.user, keys)
            ssh.newSFTPClient().use { sftp ->
                runCatching { sftp.mkdirs(remoteDir) }  // garante a pasta de recebidos
                sftp.put(localPath, dest)  // sobe; raiz SFTP do Windows = home do usuario
            }
            Result.success(dest)
        } catch (e: Exception) {
            Log.e(TAG, "Falha no upload SFTP", e)
            Result.failure(e)
        } finally {
            runCatching { ssh.disconnect() }
        }
    }

    /**
     * Monta o comando remoto. Se o caminho do agente for um .exe (instalado via
     * MSI/Inno), roda direto; senão usa `python "<script.py>"` (modo dev).
     */
    private fun remoteCmd(agentPath: String, arg: String): String =
        if (agentPath.trim().endsWith(".exe", ignoreCase = true)) {
            "\"${agentPath.trim()}\" $arg"
        } else {
            "python \"$agentPath\" $arg"
        }

    private companion object {
        const val TAG = "SshHandoff"
        val JSON = Json { ignoreUnknownKeys = true }
    }
}

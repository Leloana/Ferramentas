package com.firepot.ecossistema.net

import android.util.Base64
import android.util.Log
import net.schmizz.sshj.common.Buffer
import net.schmizz.sshj.transport.verification.HostKeyVerifier
import net.schmizz.sshj.transport.verification.PromiscuousVerifier
import java.security.MessageDigest
import java.security.PublicKey

/**
 * Verificador de host key com PINNING por fingerprint (proposta B / divida de
 * seguranca da secao 5 do MELHORIAS_APPLE.md). Compara o "SHA256:<base64>" da
 * host key apresentada com o fixado no pareamento (vindo do QR). Substitui o
 * PromiscuousVerifier (que aceitava QUALQUER host = vulneravel a MITM na LAN).
 *
 * O fingerprint e calculado igual ao `ssh-keygen -lf` e ao lado PC
 * (pareamento.py): SHA256 sobre os BYTES de fio da chave publica, base64 sem '='.
 */
class PinnedHostKeyVerifier(expectedFingerprint: String) : HostKeyVerifier {

    private val expected = expectedFingerprint.trim()

    override fun verify(hostname: String, port: Int, key: PublicKey): Boolean {
        val atual = fingerprintOf(key)
        val ok = constantTimeEquals(atual, expected)
        if (!ok) {
            Log.w(TAG, "Host key NAO confere: esperado=$expected atual=$atual ($hostname:$port)")
        }
        return ok
    }

    override fun findExistingAlgorithms(hostname: String, port: Int): MutableList<String> =
        mutableListOf()

    private companion object {
        const val TAG = "PinnedHostKey"

        fun fingerprintOf(key: PublicKey): String {
            val wire = Buffer.PlainBuffer().putPublicKey(key).compactData
            val sha = MessageDigest.getInstance("SHA-256").digest(wire)
            val b64 = Base64.encodeToString(sha, Base64.NO_PADDING or Base64.NO_WRAP)
            return "SHA256:$b64"
        }

        fun constantTimeEquals(a: String, b: String): Boolean {
            val ba = a.toByteArray(); val bb = b.toByteArray()
            if (ba.size != bb.size) return false
            var r = 0
            for (i in ba.indices) r = r or (ba[i].toInt() xor bb[i].toInt())
            return r == 0
        }
    }
}

/**
 * Escolhe o verificador certo para uma conexao: com fingerprint fixado usa o
 * pinning; sem ele (config legada, antes do pareamento) cai no Promiscuous para
 * nao quebrar quem ja usa chave colada na mao.
 */
object HostKeyVerifiers {
    fun forFingerprint(fingerprint: String?): HostKeyVerifier =
        if (!fingerprint.isNullOrBlank()) PinnedHostKeyVerifier(fingerprint)
        else PromiscuousVerifier()
}

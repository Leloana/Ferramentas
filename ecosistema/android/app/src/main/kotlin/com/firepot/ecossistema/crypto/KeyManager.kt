package com.firepot.ecossistema.crypto

import android.content.Context
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import org.bouncycastle.crypto.generators.Ed25519KeyPairGenerator
import org.bouncycastle.crypto.params.Ed25519KeyGenerationParameters
import org.bouncycastle.crypto.params.Ed25519PrivateKeyParameters
import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters
import org.bouncycastle.crypto.util.OpenSSHPrivateKeyUtil
import org.bouncycastle.crypto.util.OpenSSHPublicKeyUtil
import java.security.SecureRandom

/**
 * Gera e guarda a chave SSH do celular (proposta B).
 *
 * Decisao do projeto (pragmatica): geramos um par ed25519 no app e guardamos a
 * privada CIFRADA via EncryptedSharedPreferences (chave-mestra no Android
 * Keystore). Isso elimina o PEM colado na mao e encaixa direto no sshj (que le
 * o formato "OPENSSH PRIVATE KEY"). Keystore hardware-nao-exportavel + sshj e
 * espinhoso (sshj precisa assinar com a chave bruta), por isso ficou de fora.
 *
 * A privada existe em memoria so na hora de autenticar; em repouso fica cifrada.
 */
object KeyManager {

    private const val PREFS = "ecossistema_secure"
    private const val K_PRIV = "ssh_private_pem"
    private const val K_PUB = "ssh_public_line"
    private const val COMENTARIO = "ecossistema"

    private fun prefs(context: Context) = EncryptedSharedPreferences.create(
        context,
        PREFS,
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    // Leituras sao defensivas: se o cofre falhar ao abrir, devolvem vazio/false
    // para nao derrubar o fluxo de config (cai para a chave colada legada).
    fun hasKey(context: Context): Boolean =
        runCatching { !prefs(context).getString(K_PRIV, null).isNullOrBlank() }.getOrDefault(false)

    /** Privada em PEM OpenSSH (para sshj), ou "" se ainda nao houver. */
    fun privateKeyPem(context: Context): String =
        runCatching { prefs(context).getString(K_PRIV, "") ?: "" }.getOrDefault("")

    /** Linha de chave publica no formato authorized_keys ("ssh-ed25519 ..."). */
    fun publicKeyLine(context: Context): String =
        runCatching { prefs(context).getString(K_PUB, "") ?: "" }.getOrDefault("")

    /**
     * Garante que existe um par de chaves; gera na primeira vez. Retorna a linha
     * publica (para mandar ao PC no pareamento).
     */
    fun ensureKeyPair(context: Context): String {
        val p = prefs(context)
        val existente = p.getString(K_PUB, null)
        if (!existente.isNullOrBlank() && !p.getString(K_PRIV, null).isNullOrBlank()) {
            return existente
        }
        val gen = Ed25519KeyPairGenerator().apply {
            init(Ed25519KeyGenerationParameters(SecureRandom()))
        }
        val kp = gen.generateKeyPair()
        val priv = kp.private as Ed25519PrivateKeyParameters
        val pub = kp.public as Ed25519PublicKeyParameters

        val pem = wrapPem(OpenSSHPrivateKeyUtil.encodePrivateKey(priv))
        val pubB64 = Base64.encodeToString(OpenSSHPublicKeyUtil.encodePublicKey(pub), Base64.NO_WRAP)
        val pubLine = "ssh-ed25519 $pubB64 $COMENTARIO"

        p.edit().putString(K_PRIV, pem).putString(K_PUB, pubLine).apply()
        return pubLine
    }

    /** Embrulha os bytes da chave OpenSSH no envelope PEM que o sshj le. */
    private fun wrapPem(der: ByteArray): String {
        val b64 = Base64.encodeToString(der, Base64.NO_WRAP)
        val corpo = b64.chunked(70).joinToString("\n")
        return "-----BEGIN OPENSSH PRIVATE KEY-----\n$corpo\n-----END OPENSSH PRIVATE KEY-----\n"
    }
}

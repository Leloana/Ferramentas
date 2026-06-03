package com.firepot.ecossistema

import android.app.Application
import net.schmizz.sshj.common.SecurityUtils
import org.bouncycastle.jce.provider.BouncyCastleProvider
import java.security.Security

/**
 * Application base. Faz o "conserto de cripto" do sshj no Android:
 *
 * O Android registra um provider chamado "BC" que e uma versao REDUZIDA do
 * BouncyCastle (sem X25519/curve25519, Ed25519 etc.). Quando o sshj negocia a
 * troca de chaves (curve25519-sha256) ele pede "X25519" ao provider "BC" e toma
 * "no such algorithm X25519 for provider bc". A correcao e remover o "BC" do
 * sistema e inserir o BouncyCastle COMPLETO (que ja vem com o sshj) no topo,
 * antes de qualquer conexao SSH acontecer.
 */
class EcossistemaApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Security.removeProvider("BC")
        Security.insertProviderAt(BouncyCastleProvider(), 1)
        SecurityUtils.setRegisterBouncyCastle(true)
        SecurityUtils.setSecurityProvider("BC")
    }
}

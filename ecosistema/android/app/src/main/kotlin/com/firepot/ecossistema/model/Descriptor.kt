package com.firepot.ecossistema.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Descritor de handoff — independente de plataforma (PLANO.md secao 4).
 * O agente.py do PC consome exatamente este JSON (1 por linha).
 */
@Serializable
data class Descriptor(
    val tipo: String,
    @SerialName("app_origem") val appOrigem: String,
    val dados: Map<String, JsonElement>,
    val timestamp: Long,
) {
    fun toJsonLine(): String = JSON.encodeToString(this)

    companion object {
        /** tipos validos da tabela curada (espelha HANDLERS em agente.py). */
        const val TIPO_MIDIA = "midia"
        const val TIPO_URL = "url"
        const val TIPO_ARQUIVO = "arquivo"
        const val TIPO_PASTA = "pasta"
        const val TIPO_TEXTO = "texto"
        const val TIPO_MAPA = "mapa"
        const val TIPO_CONTATO = "contato"
        const val TIPO_APP = "app"

        private val JSON = Json { encodeDefaults = true }

        private fun nowSeconds(): Long = System.currentTimeMillis() / 1000

        private fun obj(vararg pairs: Pair<String, JsonElement>): Map<String, JsonElement> =
            JsonObject(pairs.toMap())

        fun url(url: String, appOrigem: String = "android"): Descriptor =
            Descriptor(TIPO_URL, appOrigem, obj("url" to JsonPrimitive(url)), nowSeconds())

        fun midia(url: String, posSegundos: Int? = null, appOrigem: String = "android"): Descriptor {
            val dados = mutableMapOf<String, JsonElement>("url" to JsonPrimitive(url))
            if (posSegundos != null && posSegundos > 0) {
                dados["pos_segundos"] = JsonPrimitive(posSegundos)
            }
            return Descriptor(TIPO_MIDIA, appOrigem, dados, nowSeconds())
        }

        fun pasta(caminho: String, appOrigem: String = "android"): Descriptor =
            Descriptor(TIPO_PASTA, appOrigem, obj("caminho" to JsonPrimitive(caminho)), nowSeconds())

        fun arquivo(caminho: String, appOrigem: String = "android"): Descriptor =
            Descriptor(TIPO_ARQUIVO, appOrigem, obj("caminho" to JsonPrimitive(caminho)), nowSeconds())

        fun texto(conteudo: String, appOrigem: String = "android"): Descriptor =
            Descriptor(TIPO_TEXTO, appOrigem, obj("conteudo" to JsonPrimitive(conteudo)), nowSeconds())

        fun mapa(query: String, appOrigem: String = "android"): Descriptor =
            Descriptor(TIPO_MAPA, appOrigem, obj("query" to JsonPrimitive(query)), nowSeconds())

        fun app(caminho: String, nome: String, appOrigem: String = "android"): Descriptor =
            Descriptor(
                TIPO_APP, appOrigem,
                obj("caminho" to JsonPrimitive(caminho), "nome" to JsonPrimitive(nome)),
                nowSeconds(),
            )

        /** Abre no PC um arquivo recebido via SFTP (rel = caminho relativo ao home). */
        fun abrirArquivo(rel: String, appOrigem: String = "android"): Descriptor =
            Descriptor("abrir_arquivo", appOrigem, obj("rel" to JsonPrimitive(rel)), nowSeconds())
    }
}

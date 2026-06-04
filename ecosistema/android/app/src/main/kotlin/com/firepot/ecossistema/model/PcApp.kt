package com.firepot.ecossistema.model

import kotlinx.serialization.Serializable

/** Um app do PC (atalho do Menu Iniciar), retornado por `agente.py --list-apps`. */
@Serializable
data class PcApp(val nome: String, val caminho: String)

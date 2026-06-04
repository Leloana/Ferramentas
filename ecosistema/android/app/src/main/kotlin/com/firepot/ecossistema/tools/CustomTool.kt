package com.firepot.ecossistema.tools

import kotlinx.serialization.Serializable

/**
 * Ferramenta personalizada criada pelo usuário: abre um app específico do PC.
 * O [id] é único ("app:<uuid>") e também entra no conjunto de ferramentas
 * habilitadas; [caminho] é o atalho .lnk/.url no PC.
 */
@Serializable
data class CustomTool(
    val id: String,
    val nome: String,
    val caminho: String,
)

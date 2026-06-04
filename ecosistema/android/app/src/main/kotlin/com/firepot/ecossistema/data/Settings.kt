package com.firepot.ecossistema.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.firepot.ecossistema.tools.CustomTool
import com.firepot.ecossistema.tools.HandoffTool
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "ecossistema")

/**
 * Configuracao do app: como alcancar o Agente Windows (host/usuario/porta/chave)
 * e o caminho do agente.py no PC. Persistida via DataStore.
 *
 * Transporte espelha a ponte Termux: SSH executando `python agente.py --send`
 * com o descritor na STDIN. Por isso precisamos de host/user/port/chave + path.
 */
data class PcConfig(
    val host: String = "",
    val user: String = "",
    val port: Int = 22,
    val agentPath: String = """C:\Users\mf827\Documents\Ferramentas\ecosistema\agente.py""",
    val privateKeyPem: String = "",
) {
    val isComplete: Boolean
        get() = host.isNotBlank() && user.isNotBlank() && privateKeyPem.isNotBlank()
}

class Settings(private val context: Context) {

    val pcConfig: Flow<PcConfig> = context.dataStore.data.map { prefs ->
        PcConfig(
            host = prefs[KEY_HOST] ?: "",
            user = prefs[KEY_USER] ?: "",
            port = prefs[KEY_PORT]?.toIntOrNull() ?: 22,
            agentPath = prefs[KEY_AGENT_PATH]
                ?: """C:\Users\mf827\Documents\Ferramentas\ecosistema\agente.py""",
            privateKeyPem = prefs[KEY_KEY] ?: "",
        )
    }

    suspend fun current(): PcConfig = pcConfig.first()

    /** Conjunto de IDs de ferramentas habilitadas no overlay (default: todas). */
    val enabledTools: Flow<Set<String>> = context.dataStore.data.map { prefs ->
        prefs[KEY_TOOLS] ?: HandoffTool.DEFAULT_ENABLED
    }

    suspend fun setToolEnabled(id: String, enabled: Boolean) {
        context.dataStore.edit { prefs ->
            val cur = (prefs[KEY_TOOLS] ?: HandoffTool.DEFAULT_ENABLED).toMutableSet()
            if (enabled) cur.add(id) else cur.remove(id)
            prefs[KEY_TOOLS] = cur
        }
    }

    /** Ferramentas personalizadas (abrir um app específico do PC). */
    val customTools: Flow<List<CustomTool>> = context.dataStore.data.map { prefs ->
        decodeCustom(prefs[KEY_CUSTOM])
    }

    suspend fun addCustomTool(tool: CustomTool) {
        context.dataStore.edit { prefs ->
            val cur = decodeCustom(prefs[KEY_CUSTOM]).filter { it.id != tool.id } + tool
            prefs[KEY_CUSTOM] = JSON.encodeToString(cur)
            // Já habilita no overlay por padrão.
            val en = (prefs[KEY_TOOLS] ?: HandoffTool.DEFAULT_ENABLED).toMutableSet()
            en.add(tool.id)
            prefs[KEY_TOOLS] = en
        }
    }

    suspend fun removeCustomTool(id: String) {
        context.dataStore.edit { prefs ->
            val cur = decodeCustom(prefs[KEY_CUSTOM]).filter { it.id != id }
            prefs[KEY_CUSTOM] = JSON.encodeToString(cur)
            val en = (prefs[KEY_TOOLS] ?: HandoffTool.DEFAULT_ENABLED).toMutableSet()
            en.remove(id)
            prefs[KEY_TOOLS] = en
        }
    }

    private fun decodeCustom(raw: String?): List<CustomTool> =
        if (raw.isNullOrBlank()) emptyList()
        else runCatching { JSON.decodeFromString<List<CustomTool>>(raw) }.getOrDefault(emptyList())

    suspend fun save(config: PcConfig) {
        context.dataStore.edit { prefs ->
            prefs[KEY_HOST] = config.host
            prefs[KEY_USER] = config.user
            prefs[KEY_PORT] = config.port.toString()
            prefs[KEY_AGENT_PATH] = config.agentPath
            prefs[KEY_KEY] = config.privateKeyPem
        }
    }

    private companion object {
        val KEY_HOST = stringPreferencesKey("pc_host")
        val KEY_USER = stringPreferencesKey("pc_user")
        val KEY_PORT = stringPreferencesKey("pc_port")
        val KEY_AGENT_PATH = stringPreferencesKey("pc_agent_path")
        val KEY_KEY = stringPreferencesKey("pc_private_key")
        val KEY_TOOLS = stringSetPreferencesKey("enabled_tools")
        val KEY_CUSTOM = stringPreferencesKey("custom_tools")
        val JSON = Json { ignoreUnknownKeys = true }
    }
}

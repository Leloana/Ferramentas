package com.firepot.ecossistema.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

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
    }
}

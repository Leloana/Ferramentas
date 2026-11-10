package app.despertador

import android.content.Context

/** Configuração local do app (SharedPreferences). */
class Prefs(ctx: Context) {
    private val sp = ctx.getSharedPreferences("despertador", Context.MODE_PRIVATE)

    var servidor: String
        get() = sp.getString("servidor", "") ?: ""
        set(v) = sp.edit().putString("servidor", v.trim().trimEnd('/')).apply()

    var token: String
        get() = sp.getString("token", "") ?: ""
        set(v) = sp.edit().putString("token", v.trim()).apply()

    var hora: Int
        get() = sp.getInt("hora", 7)
        set(v) = sp.edit().putInt("hora", v).apply()

    var minuto: Int
        get() = sp.getInt("minuto", 0)
        set(v) = sp.edit().putInt("minuto", v).apply()

    /** Dias ativos, 1 = segunda ... 7 = domingo (java.time.DayOfWeek). */
    var dias: Set<Int>
        get() = (sp.getStringSet("dias", setOf("1", "2", "3", "4", "5")) ?: emptySet()).map { it.toInt() }.toSet()
        set(v) = sp.edit().putStringSet("dias", v.map { it.toString() }.toSet()).apply()

    var ativo: Boolean
        get() = sp.getBoolean("ativo", false)
        set(v) = sp.edit().putBoolean("ativo", v).apply()

    /** Disparo pontual (soneca ou teste), em epoch ms; 0 = nenhum. */
    var pontual: Long
        get() = sp.getLong("pontual", 0L)
        set(v) = sp.edit().putLong("pontual", v).apply()

    var ultimaSync: Long
        get() = sp.getLong("ultima_sync", 0L)
        set(v) = sp.edit().putLong("ultima_sync", v).apply()

    var statusSync: String
        get() = sp.getString("status_sync", "Nunca sincronizado") ?: ""
        set(v) = sp.edit().putString("status_sync", v).apply()

    var ultimoToque: String
        get() = sp.getString("ultimo_toque", "") ?: ""
        set(v) = sp.edit().putString("ultimo_toque", v).apply()
}

package app.despertador

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.TimePicker
import android.widget.Toast
import java.text.SimpleDateFormat
import java.time.format.DateTimeFormatter
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {

    private lateinit var p: Prefs
    private lateinit var status: TextView
    private val br = Locale("pt", "BR")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        p = Prefs(this)
        setContentView(montarTela())
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        SyncJob.agendar(this)
        Agendador.reagendar(this)
    }

    override fun onResume() {
        super.onResume()
        atualizarStatus()
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun montarTela(): View {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(24), dp(20), dp(32))
        }
        fun titulo(t: String, tam: Float = 18f) = TextView(this).apply {
            text = t; textSize = tam; setTypeface(typeface, Typeface.BOLD); setPadding(0, dp(18), 0, dp(6))
        }.also { col.addView(it) }
        fun botao(t: String, acao: () -> Unit) = Button(this).apply {
            text = t; isAllCaps = false; setOnClickListener { acao() }
        }.also { col.addView(it, LinearLayout.LayoutParams(-1, -2)) }

        titulo("Despertador", 26f).setPadding(0, 0, 0, dp(4))
        status = TextView(this).apply { textSize = 15f; setLineSpacing(0f, 1.25f) }
        col.addView(status)

        // ---- Alarme
        titulo("Alarme")
        val relogio = TimePicker(this).apply {
            setIs24HourView(true)
            hour = p.hora; minute = p.minuto
        }
        col.addView(relogio)

        val nomes = listOf("S", "T", "Q", "Q", "S", "S", "D")
        val linhaDias = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        val caixas = nomes.mapIndexed { i, n ->
            CheckBox(this).apply { text = n; isChecked = (i + 1) in p.dias }.also {
                linhaDias.addView(it, LinearLayout.LayoutParams(0, -2, 1f))
            }
        }
        col.addView(linhaDias)

        val ligado = Switch(this).apply { text = "Alarme ligado"; textSize = 16f; isChecked = p.ativo }
        col.addView(ligado, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })

        botao("Salvar alarme") {
            p.hora = relogio.hour; p.minuto = relogio.minute
            p.dias = caixas.mapIndexedNotNull { i, c -> if (c.isChecked) i + 1 else null }.toSet()
            p.ativo = ligado.isChecked
            Agendador.reagendar(this)
            atualizarStatus()
            aviso("Alarme salvo")
        }
        botao("Testar em 1 minuto") {
            Agendador.agendarPontual(this, 60_000)
            atualizarStatus()
            aviso("Vai tocar em 1 minuto. Pode bloquear a tela.")
        }
        botao("Tocar agora") {
            startForegroundService(Intent(this, AlarmService::class.java).setAction(AlarmService.ACAO_TOCAR))
        }
        botao("Parar") {
            startService(Intent(this, AlarmService::class.java).setAction(AlarmService.ACAO_PARAR))
        }

        // ---- Servidor
        titulo("Servidor")
        val endereco = EditText(this).apply {
            hint = "http://192.168.15.6:8040"; setText(p.servidor)
            inputType = InputType.TYPE_TEXT_VARIATION_URI; isSingleLine = true
        }
        val token = EditText(this).apply {
            hint = "token do aparelho"; setText(p.token)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS; isSingleLine = true
        }
        col.addView(endereco); col.addView(token)
        botao("Salvar e sincronizar") {
            p.servidor = endereco.text.toString(); p.token = token.text.toString()
            p.statusSync = "Sincronizando..."
            atualizarStatus()
            Thread {
                val msg = Edicoes.sincronizar(this)
                runOnUiThread { atualizarStatus(); aviso(msg) }
            }.start()
        }

        return ScrollView(this).apply { addView(col) }
    }

    private fun atualizarStatus() {
        val linhas = mutableListOf<String>()
        val prox = Agendador.proximo(this)
        linhas += when {
            !Agendador.podeAgendar(this) -> "⚠ Sem permissão de alarme exato: o alarme NÃO está pronto."
            prox == null -> "Nenhum alarme agendado."
            else -> "⏰ Próximo: " + SimpleDateFormat("EEE dd/MM 'às' HH:mm", br).format(Date(prox))
        }
        val ed = Edicoes.atual(this)
        linhas += when {
            ed == null -> "📰 Sem jornal baixado (vai tocar o aviso + toque)."
            ed.vencida -> "📰 Jornal ${ed.dataEditorial} VENCIDO (vai tocar o aviso)."
            else -> "📰 Jornal ${ed.dataEditorial} pronto, vale até " +
                (ed.expiraEm?.format(DateTimeFormatter.ofPattern("dd/MM HH:mm")) ?: "?") +
                (if (ed.arquivo("music") != null) " + música" else "")
        }
        val sync = if (p.ultimaSync == 0L) "nunca" else SimpleDateFormat("dd/MM HH:mm", br).format(Date(p.ultimaSync))
        linhas += "🔄 Última sincronização ok: $sync"
        linhas += "   ${p.statusSync}"
        if (p.ultimoToque.isNotBlank()) linhas += "🔔 Último toque: ${p.ultimoToque}"
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) linhas += "⚠ Notificações desligadas: o botão Parar não aparece na tela de bloqueio."
        status.text = linhas.joinToString("\n")
    }

    private fun aviso(t: String) = Toast.makeText(this, t, Toast.LENGTH_LONG).show()
}

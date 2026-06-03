package com.firepot.ecossistema.overlay

import android.app.Service
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import com.firepot.ecossistema.R
import com.firepot.ecossistema.handoff.HandoffManager
import com.firepot.ecossistema.model.Descriptor
import com.firepot.ecossistema.service.HandoffAccessibilityService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlin.math.abs

/**
 * Overlay "AssistiveTouch": uma bolha flutuante sempre sobre os outros apps.
 *  - TOCAR a bolha  -> abre/fecha o leque de atalhos.
 *  - ARRASTAR        -> reposiciona; ao soltar, gruda na borda esquerda/direita.
 *  - tocar FORA       -> recolhe o leque (FLAG_WATCH_OUTSIDE_TOUCH).
 *
 * Atalhos: "Link da tela" (URL em foco lida pela Acessibilidade) e
 * "Texto copiado" (clipboard do Android). Cada um monta o descritor e envia ao
 * PC via [HandoffManager]. Requer SYSTEM_ALERT_WINDOW concedido.
 */
class CornerOverlayService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var windowManager: WindowManager
    private lateinit var params: WindowManager.LayoutParams
    private var root: LinearLayout? = null
    private var menu: LinearLayout? = null
    private var expanded = false

    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            Toast.makeText(
                this,
                "Conceda a permissão de sobreposição (overlay) para a bolha aparecer.",
                Toast.LENGTH_LONG,
            ).show()
            stopSelf()
            return
        }
        addOverlay()
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private fun addOverlay() {
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 0
            y = dp(120)
        }

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            // Capta toques FORA da janela (ACTION_OUTSIDE) para recolher o leque.
            setOnTouchListener { _, e ->
                if (e.actionMasked == MotionEvent.ACTION_OUTSIDE) collapse()
                false
            }
        }

        val bubble = ImageView(this).apply {
            setImageResource(R.drawable.overlay_handle)
            val s = dp(56)
            layoutParams = LinearLayout.LayoutParams(s, s)
            setOnTouchListener(BubbleTouch())
        }

        val menuView = buildMenu().apply { visibility = View.GONE }

        container.addView(bubble)
        container.addView(menuView)

        root = container
        menu = menuView

        runCatching { windowManager.addView(container, params) }
            .onFailure {
                Log.e(TAG, "Falha ao adicionar overlay", it)
                Toast.makeText(this, "Falha ao mostrar a bolha (permissão?).", Toast.LENGTH_LONG).show()
                stopSelf()
            }
    }

    private fun buildMenu(): LinearLayout {
        val pad = dp(8)
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            background = GradientDrawable().apply {
                cornerRadius = dp(16).toFloat()
                setColor(Color.parseColor("#EE222222"))
            }
            addView(actionButton("🔗  Link da tela") { sendCurrentLink() })
            addView(actionButton("📋  Texto copiado") { sendClipboard() })
        }
    }

    private fun actionButton(label: String, onClick: () -> Unit): TextView =
        TextView(this).apply {
            text = label
            setTextColor(Color.WHITE)
            textSize = 15f
            setPadding(dp(14), dp(12), dp(14), dp(12))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = dp(6) }
            background = GradientDrawable().apply {
                cornerRadius = dp(12).toFloat()
                setColor(Color.parseColor("#1565C0"))
            }
            setOnClickListener {
                collapse()
                onClick()
            }
        }

    /** Distingue toque (abre o menu) de arrasto (move + gruda na borda). */
    private inner class BubbleTouch : View.OnTouchListener {
        private var startX = 0
        private var startY = 0
        private var touchRawX = 0f
        private var touchRawY = 0f
        private var moved = false
        private val slop = ViewConfiguration.get(this@CornerOverlayService).scaledTouchSlop

        override fun onTouch(v: View, e: MotionEvent): Boolean {
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    startX = params.x
                    startY = params.y
                    touchRawX = e.rawX
                    touchRawY = e.rawY
                    moved = false
                    return true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (e.rawX - touchRawX).toInt()
                    val dy = (e.rawY - touchRawY).toInt()
                    if (abs(dx) > slop || abs(dy) > slop) moved = true
                    params.x = startX + dx
                    params.y = startY + dy
                    runCatching { windowManager.updateViewLayout(root, params) }
                    return true
                }
                MotionEvent.ACTION_UP -> {
                    if (moved) snapToEdge() else toggle()
                    return true
                }
            }
            return false
        }
    }

    private fun toggle() = if (expanded) collapse() else expand()

    private fun expand() {
        menu?.visibility = View.VISIBLE
        expanded = true
        runCatching { windowManager.updateViewLayout(root, params) }
        // Depois do layout, garante que o leque caiba na tela.
        root?.post {
            val r = root ?: return@post
            val dm = resources.displayMetrics
            var changed = false
            if (params.y + r.height > dm.heightPixels) {
                params.y = (dm.heightPixels - r.height).coerceAtLeast(0); changed = true
            }
            if (params.x + r.width > dm.widthPixels) {
                params.x = (dm.widthPixels - r.width).coerceAtLeast(0); changed = true
            }
            if (changed) runCatching { windowManager.updateViewLayout(r, params) }
        }
    }

    private fun collapse() {
        if (!expanded) return
        menu?.visibility = View.GONE
        expanded = false
        runCatching { windowManager.updateViewLayout(root, params) }
    }

    private fun snapToEdge() {
        val r = root ?: return
        val dm = resources.displayMetrics
        params.x = if (params.x + r.width / 2 < dm.widthPixels / 2) 0 else dm.widthPixels - r.width
        params.y = params.y.coerceIn(0, (dm.heightPixels - r.height).coerceAtLeast(0))
        runCatching { windowManager.updateViewLayout(r, params) }
    }

    // ---- Ações dos atalhos ----
    private fun sendCurrentLink() {
        val url = HandoffAccessibilityService.lastUrl
        if (url.isNullOrBlank()) {
            toast("Nenhuma URL em foco. Abra uma página no navegador e ative a Acessibilidade.")
            return
        }
        val descriptor = HandoffManager.fromSharedText(url)
        scope.launch { HandoffManager.send(applicationContext, descriptor) }
    }

    private fun sendClipboard() {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = cm.primaryClip
        val text = if (clip != null && clip.itemCount > 0) {
            clip.getItemAt(0).coerceToText(this).toString()
        } else {
            ""
        }
        if (text.isBlank()) {
            toast("Clipboard vazio ou sem acesso em segundo plano (limite do Android 10+).")
            return
        }
        scope.launch { HandoffManager.send(applicationContext, Descriptor.texto(text)) }
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()

    override fun onDestroy() {
        root?.let { runCatching { windowManager.removeView(it) } }
        root = null
        scope.cancel()
        super.onDestroy()
    }

    private companion object {
        const val TAG = "CornerOverlay"
    }
}

package com.firepot.ecossistema.overlay

import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.IBinder
import android.provider.Settings as AndroidSettings
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
import com.firepot.ecossistema.data.Settings
import com.firepot.ecossistema.handoff.HandoffManager
import com.firepot.ecossistema.tools.HandoffTool
import com.firepot.ecossistema.tools.ToolRunner
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlin.math.abs

/**
 * Overlay "AssistiveTouch": uma bolha flutuante sempre sobre os outros apps.
 *  - TOCAR a bolha  -> abre/fecha a LISTA de ferramentas (cada uma só com ícone).
 *  - ARRASTAR        -> reposiciona; ao soltar, gruda na borda esquerda/direita.
 *  - tocar FORA       -> recolhe a lista (FLAG_WATCH_OUTSIDE_TOUCH).
 *
 * As ferramentas exibidas são as habilitadas na aba "Ferramentas" do app
 * (persistidas em [Settings.enabledTools]). Requer SYSTEM_ALERT_WINDOW.
 */
class CornerOverlayService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var windowManager: WindowManager
    private lateinit var params: WindowManager.LayoutParams
    private lateinit var settings: Settings
    private var root: LinearLayout? = null
    private var menu: LinearLayout? = null
    private var expanded = false
    private var enabledIds: List<String> = HandoffTool.ALL.map { it.id }

    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        settings = Settings(this)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !AndroidSettings.canDrawOverlays(this)) {
            Toast.makeText(
                this,
                "Conceda a permissão de sobreposição (overlay) para a bolha aparecer.",
                Toast.LENGTH_LONG,
            ).show()
            stopSelf()
            return
        }
        addOverlay()
        // Mantém a lista de ferramentas em sincronia com o que o app habilitou.
        scope.launch {
            settings.enabledTools.collectLatest { ids ->
                enabledIds = HandoffTool.ALL.map { it.id }.filter { it in ids }
                rebuildMenu()
            }
        }
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
            gravity = Gravity.CENTER_HORIZONTAL
            // Capta toques FORA da janela (ACTION_OUTSIDE) para recolher a lista.
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

        val menuView = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            visibility = View.GONE
        }

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

    /** Recria os botões (só ícone) a partir das ferramentas habilitadas. */
    private fun rebuildMenu() {
        val m = menu ?: return
        m.removeAllViews()
        for (id in enabledIds) {
            val tool = HandoffTool.byId(id) ?: continue
            m.addView(iconButton(tool))
        }
    }

    private fun iconButton(tool: HandoffTool): TextView =
        TextView(this).apply {
            text = tool.icon
            textSize = 22f
            gravity = Gravity.CENTER
            val s = dp(52)
            layoutParams = LinearLayout.LayoutParams(s, s).apply { topMargin = dp(8) }
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.parseColor("#EE1565C0"))
                setStroke(dp(2), Color.WHITE)
            }
            setOnClickListener {
                collapse()
                runTool(tool.id)
            }
        }

    private fun runTool(toolId: String) {
        val descriptor = ToolRunner.buildDescriptor(this, toolId) ?: return
        scope.launch { HandoffManager.send(applicationContext, descriptor) }
    }

    /** Distingue toque (abre a lista) de arrasto (move + gruda na borda). */
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

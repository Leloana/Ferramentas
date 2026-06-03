package com.firepot.ecossistema.overlay

import android.app.Service
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.util.Log
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.ImageView
import com.firepot.ecossistema.R
import com.firepot.ecossistema.handoff.HandoffManager
import com.firepot.ecossistema.model.Descriptor
import com.firepot.ecossistema.service.HandoffAccessibilityService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Overlay "arrastar pro canto" (PLANO.md secao 1/2): um "handle" flutuante.
 * Ao arrastar e soltar num canto da tela, dispara o handoff do app em foco
 * (lido via [HandoffAccessibilityService]) para o PC.
 *
 * Requer SYSTEM_ALERT_WINDOW concedido (Settings.canDrawOverlays).
 */
class CornerOverlayService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var windowManager: WindowManager
    private var handle: View? = null
    private lateinit var params: WindowManager.LayoutParams

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        addHandle()
    }

    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    private fun addHandle() {
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
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 0
            y = 300
        }

        val view = ImageView(this).apply {
            setImageResource(R.drawable.overlay_handle)
            setOnTouchListener(DragListener())
        }
        handle = view
        runCatching { windowManager.addView(view, params) }
            .onFailure { Log.e(TAG, "Falha ao adicionar overlay (permissao?)", it) }
    }

    /** Arrasta o handle; ao soltar num canto, dispara o handoff. */
    private inner class DragListener : View.OnTouchListener {
        private var initialX = 0
        private var initialY = 0
        private var touchX = 0f
        private var touchY = 0f

        override fun onTouch(v: View, e: MotionEvent): Boolean {
            when (e.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    touchX = e.rawX
                    touchY = e.rawY
                    return true
                }
                MotionEvent.ACTION_MOVE -> {
                    params.x = initialX + (e.rawX - touchX).toInt()
                    params.y = initialY + (e.rawY - touchY).toInt()
                    runCatching { windowManager.updateViewLayout(v, params) }
                    return true
                }
                MotionEvent.ACTION_UP -> {
                    if (droppedInCorner(e.rawX, e.rawY)) {
                        triggerHandoff()
                    }
                    return true
                }
            }
            return false
        }
    }

    private fun droppedInCorner(x: Float, y: Float): Boolean {
        val dm = resources.displayMetrics
        val marginX = dm.widthPixels * CORNER_FRACTION
        val marginY = dm.heightPixels * CORNER_FRACTION
        val nearLeftOrRight = x <= marginX || x >= dm.widthPixels - marginX
        val nearTopOrBottom = y <= marginY || y >= dm.heightPixels - marginY
        return nearLeftOrRight && nearTopOrBottom
    }

    /** Monta o descritor a partir do app/URL em foco e envia ao PC. */
    private fun triggerHandoff() {
        val url = HandoffAccessibilityService.lastUrl
        val pkg = HandoffAccessibilityService.lastForegroundPackage ?: "android"
        val descriptor: Descriptor? = when {
            url != null && (url.contains("youtube.com/") || url.contains("youtu.be/")) ->
                Descriptor.midia(url, appOrigem = pkg)
            url != null -> Descriptor.url(url, appOrigem = pkg)
            else -> null
        }
        if (descriptor == null) {
            Log.w(TAG, "Sem URL em foco para handoff (acessibilidade ativa?)")
            return
        }
        scope.launch { HandoffManager.send(applicationContext, descriptor) }
    }

    override fun onDestroy() {
        handle?.let { runCatching { windowManager.removeView(it) } }
        handle = null
        scope.cancel()
        super.onDestroy()
    }

    private companion object {
        const val TAG = "CornerOverlay"
        const val CORNER_FRACTION = 0.18f
    }
}

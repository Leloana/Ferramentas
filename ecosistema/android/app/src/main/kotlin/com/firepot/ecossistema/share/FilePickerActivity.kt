package com.firepot.ecossistema.share

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.lifecycle.lifecycleScope
import com.firepot.ecossistema.handoff.HandoffManager
import kotlinx.coroutines.launch

/**
 * Activity translúcida disparada pela ferramenta "Enviar arquivo" da bolha:
 * abre o seletor de arquivos do sistema e sobe o escolhido pro PC via SFTP.
 */
class FilePickerActivity : ComponentActivity() {

    private val picker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            lifecycleScope.launch {
                HandoffManager.sendFile(applicationContext, uri)
                finish()
            }
        } else {
            finish()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        picker.launch(arrayOf("*/*"))
    }
}

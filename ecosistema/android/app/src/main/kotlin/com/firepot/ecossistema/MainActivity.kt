package com.firepot.ecossistema

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings as AndroidSettings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Divider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.firepot.ecossistema.data.PcConfig
import com.firepot.ecossistema.data.Settings
import com.firepot.ecossistema.handoff.HandoffManager
import com.firepot.ecossistema.model.Descriptor
import com.firepot.ecossistema.service.HandoffForegroundService
import com.firepot.ecossistema.ui.theme.EcossistemaTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        maybeRequestNotifications()
        setContent {
            EcossistemaTheme {
                Scaffold { padding ->
                    HomeScreen(Modifier.padding(padding))
                }
            }
        }
    }

    /** Pede POST_NOTIFICATIONS (Android 13+) p/ a notificacao persistente do FGS aparecer. */
    private fun maybeRequestNotifications() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIF)
        }
    }

    private companion object {
        const val REQ_NOTIF = 1001
    }
}

@Composable
private fun HomeScreen(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = remember { Settings(context) }

    var host by remember { mutableStateOf("") }
    var user by remember { mutableStateOf("") }
    var port by remember { mutableStateOf("22") }
    var agentPath by remember { mutableStateOf("") }
    var privateKey by remember { mutableStateOf("") }
    var loaded by remember { mutableStateOf(false) }

    // Carrega a config persistida uma vez.
    if (!loaded) {
        scope.launch {
            val c = settings.current()
            host = c.host
            user = c.user
            port = c.port.toString()
            agentPath = c.agentPath
            privateKey = c.privateKeyPem
        }
        loaded = true
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("Ecossistema — Marco 1", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Handoff Android → PC. Configure o acesso ao Agente Windows e conceda " +
                "as permissoes do gesto.",
            style = MaterialTheme.typography.bodyMedium,
        )

        Divider()
        Text("Conexao com o PC", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(host, { host = it }, label = { Text("Host (IP LAN ou 100.x Tailscale)") },
            modifier = Modifier.fillMaxWidth())
        OutlinedTextField(user, { user = it }, label = { Text("Usuario do Windows") },
            modifier = Modifier.fillMaxWidth())
        OutlinedTextField(port, { port = it }, label = { Text("Porta SSH") },
            modifier = Modifier.fillMaxWidth())
        OutlinedTextField(agentPath, { agentPath = it }, label = { Text("Caminho do agente.py") },
            modifier = Modifier.fillMaxWidth())
        OutlinedTextField(privateKey, { privateKey = it },
            label = { Text("Chave privada (PEM) — id_ed25519") },
            modifier = Modifier.fillMaxWidth())
        Button(
            onClick = {
                scope.launch {
                    settings.save(
                        PcConfig(
                            host = host.trim(),
                            user = user.trim(),
                            port = port.trim().toIntOrNull() ?: 22,
                            agentPath = agentPath.trim(),
                            privateKeyPem = privateKey.trim(),
                        ),
                    )
                    Toast.makeText(context, "Conexão salva", Toast.LENGTH_SHORT).show()
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Salvar conexao") }

        Divider()
        Text("Permissoes do gesto", style = MaterialTheme.typography.titleMedium)
        OutlinedButton({ openOverlaySettings(context) }, Modifier.fillMaxWidth()) {
            Text("1. Permitir sobreposicao (overlay)")
        }
        OutlinedButton({ openAccessibilitySettings(context) }, Modifier.fillMaxWidth()) {
            Text("2. Ativar Acessibilidade (ler app em foco)")
        }
        OutlinedButton({ openUsageAccessSettings(context) }, Modifier.fillMaxWidth()) {
            Text("3. Acesso de uso (UsageStats)")
        }
        OutlinedButton({ openBatterySettings(context) }, Modifier.fillMaxWidth()) {
            Text("4. Ignorar otimizacao de bateria")
        }

        Divider()
        Text("Servico", style = MaterialTheme.typography.titleMedium)
        Button({ HandoffForegroundService.start(context) }, Modifier.fillMaxWidth()) {
            Text("Iniciar servico + overlay")
        }
        OutlinedButton({ HandoffForegroundService.stop(context) }, Modifier.fillMaxWidth()) {
            Text("Parar servico")
        }

        Divider()
        Text("Testes rapidos", style = MaterialTheme.typography.titleMedium)
        Button(
            onClick = {
                scope.launch {
                    HandoffManager.send(context, Descriptor.url("https://example.com"))
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Testar: abrir link no PC") }
        Button(
            onClick = {
                scope.launch {
                    HandoffManager.send(
                        context,
                        Descriptor.midia("https://youtu.be/dQw4w9WgXcQ", posSegundos = 42),
                    )
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Testar: YouTube com timestamp") }
    }
}

// ---- Helpers de permissao (abrem as telas do sistema) ----
private fun openOverlaySettings(context: Context) {
    val intent = Intent(
        AndroidSettings.ACTION_MANAGE_OVERLAY_PERMISSION,
        Uri.parse("package:${context.packageName}"),
    ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    context.startActivity(intent)
}

private fun openAccessibilitySettings(context: Context) {
    context.startActivity(
        Intent(AndroidSettings.ACTION_ACCESSIBILITY_SETTINGS)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}

private fun openUsageAccessSettings(context: Context) {
    context.startActivity(
        Intent(AndroidSettings.ACTION_USAGE_ACCESS_SETTINGS)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}

private fun openBatterySettings(context: Context) {
    val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
        Intent(
            AndroidSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
            Uri.parse("package:${context.packageName}"),
        )
    } else {
        Intent(AndroidSettings.ACTION_SETTINGS)
    }
    context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

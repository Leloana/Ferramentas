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
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.firepot.ecossistema.data.PcConfig
import com.firepot.ecossistema.data.Settings
import com.firepot.ecossistema.handoff.HandoffManager
import com.firepot.ecossistema.service.HandoffForegroundService
import com.firepot.ecossistema.tools.HandoffTool
import com.firepot.ecossistema.ui.theme.EcossistemaTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        maybeRequestNotifications()
        setContent {
            EcossistemaTheme {
                Scaffold { padding ->
                    var tab by remember { mutableIntStateOf(0) }
                    Column(Modifier.fillMaxSize().padding(padding)) {
                        TabRow(selectedTabIndex = tab) {
                            Tab(tab == 0, onClick = { tab = 0 }, text = { Text("Início") })
                            Tab(tab == 1, onClick = { tab = 1 }, text = { Text("Ferramentas") })
                        }
                        when (tab) {
                            0 -> HomeScreen()
                            else -> ToolsScreen()
                        }
                    }
                }
            }
        }
    }

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

private enum class ConnStatus { CHECKING, OK, FAIL, UNCONFIGURED }

@Composable
private fun HomeScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = remember { Settings(context) }

    var host by remember { mutableStateOf("") }
    var user by remember { mutableStateOf("") }
    var port by remember { mutableStateOf("22") }
    var agentPath by remember { mutableStateOf("") }
    var privateKey by remember { mutableStateOf("") }
    var loaded by remember { mutableStateOf(false) }

    var serviceOn by remember { mutableStateOf(HandoffForegroundService.isRunning) }
    var recheck by remember { mutableIntStateOf(0) }
    var status by remember { mutableStateOf(ConnStatus.UNCONFIGURED) }
    var stHost by remember { mutableStateOf("") }
    var stUser by remember { mutableStateOf("") }

    if (!loaded) {
        scope.launch {
            val c = settings.current()
            host = c.host; user = c.user; port = c.port.toString()
            agentPath = c.agentPath; privateKey = c.privateKeyPem
        }
        loaded = true
    }

    LaunchedEffect(recheck) {
        val c = settings.current()
        stHost = c.host; stUser = c.user
        if (!c.isComplete) { status = ConnStatus.UNCONFIGURED; return@LaunchedEffect }
        status = ConnStatus.CHECKING
        status = if (HandoffManager.checkConnection(context).isSuccess) ConnStatus.OK else ConnStatus.FAIL
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // 1) Status do PC no topo
        ConnectionStatusCard(status, stHost, stUser) { recheck++ }

        // 2) Toggle do serviço (primeira coisa acionável)
        Card {
            Row(
                Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Bolha de atalhos", style = MaterialTheme.typography.titleMedium)
                    Text(
                        if (serviceOn) "Ligada — overlay ativo" else "Desligada",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                Switch(
                    checked = serviceOn,
                    onCheckedChange = { want ->
                        if (want) {
                            if (!canOverlay(context)) {
                                Toast.makeText(
                                    context,
                                    "Conceda a permissão de Sobreposição (overlay) primeiro.",
                                    Toast.LENGTH_LONG,
                                ).show()
                                openOverlaySettings(context)
                            } else {
                                HandoffForegroundService.start(context)
                                serviceOn = true
                            }
                        } else {
                            HandoffForegroundService.stop(context)
                            serviceOn = false
                        }
                    },
                )
            }
        }

        HorizontalDivider()
        Text("Conexão com o PC", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(host, { host = it }, label = { Text("Host (IP LAN ou 100.x Tailscale)") },
            modifier = Modifier.fillMaxWidth())
        OutlinedTextField(user, { user = it }, label = { Text("Usuário do Windows") },
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
                            host = host.trim(), user = user.trim(),
                            port = port.trim().toIntOrNull() ?: 22,
                            agentPath = agentPath.trim(), privateKeyPem = privateKey.trim(),
                        ),
                    )
                    Toast.makeText(context, "Conexão salva", Toast.LENGTH_SHORT).show()
                    recheck++
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Salvar conexão") }

        // 4) Permissões no rodapé
        HorizontalDivider()
        Text("Permissões", style = MaterialTheme.typography.titleMedium)
        Text(
            "Para a bolha funcionar você precisa das OBRIGATÓRIAS abaixo.",
            style = MaterialTheme.typography.bodySmall,
        )
        PermissionRow(
            "Sobreposição (overlay)", obrigatoria = true,
            granted = canOverlay(context),
            detail = "Faz a bolha aparecer sobre os outros apps.",
        ) { openOverlaySettings(context) }
        PermissionRow(
            "Acessibilidade", obrigatoria = true, granted = null,
            detail = "Necessária para a ferramenta \"Link da tela\" ler a URL aberta.",
        ) { openAccessibilitySettings(context) }
        PermissionRow(
            "Notificações", obrigatoria = false, granted = notificationsGranted(context),
            detail = "Mostra a notificação fixa do serviço (recomendado).",
        ) { openAppNotificationSettings(context) }
        PermissionRow(
            "Acesso de uso", obrigatoria = false, granted = null,
            detail = "Opcional: ajuda a inferir o app em foco.",
        ) { openUsageAccessSettings(context) }
        PermissionRow(
            "Ignorar otimização de bateria", obrigatoria = false, granted = null,
            detail = "Opcional: evita o sistema matar o serviço.",
        ) { openBatterySettings(context) }
    }
}

@Composable
private fun ConnectionStatusCard(status: ConnStatus, host: String, user: String, onTap: () -> Unit) {
    val (dot, titulo) = when (status) {
        ConnStatus.OK -> Color(0xFF2E7D32) to "Conectado"
        ConnStatus.FAIL -> Color(0xFFC62828) to "Sem conexão"
        ConnStatus.CHECKING -> Color(0xFFF9A825) to "Verificando…"
        ConnStatus.UNCONFIGURED -> Color(0xFF9E9E9E) to "Nenhum PC configurado"
    }
    Card(Modifier.fillMaxWidth().clickable { onTap() }) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("🖥️", style = MaterialTheme.typography.headlineMedium)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(12.dp).clip(CircleShape).background(dot))
                    Spacer(Modifier.width(8.dp))
                    Text(titulo, style = MaterialTheme.typography.titleMedium)
                }
                if (host.isNotBlank()) {
                    Text("$user@$host", style = MaterialTheme.typography.bodyMedium)
                }
                Text("toque para reverificar", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun PermissionRow(
    nome: String,
    obrigatoria: Boolean,
    granted: Boolean?,
    detail: String,
    onOpen: () -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(nome, style = MaterialTheme.typography.titleSmall)
                    Spacer(Modifier.width(8.dp))
                    val tag = if (obrigatoria) "OBRIGATÓRIA" else "opcional"
                    val tagColor = if (obrigatoria) Color(0xFFC62828) else Color(0xFF9E9E9E)
                    Text(tag, color = tagColor, style = MaterialTheme.typography.labelSmall)
                    if (granted != null) {
                        Spacer(Modifier.width(8.dp))
                        Text(if (granted) "✓ concedida" else "✗ falta",
                            color = if (granted) Color(0xFF2E7D32) else Color(0xFFC62828),
                            style = MaterialTheme.typography.labelSmall)
                    }
                }
                Text(detail, style = MaterialTheme.typography.bodySmall)
            }
            OutlinedButton(onClick = onOpen) { Text("Abrir") }
        }
    }
}

@Composable
private fun ToolsScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = remember { Settings(context) }
    val enabled by settings.enabledTools.collectAsState(initial = HandoffTool.DEFAULT_ENABLED)

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Ferramentas da bolha", style = MaterialTheme.typography.titleLarge)
        Text(
            "Ligue/desligue o que aparece no overlay. No overlay aparece só o ícone; " +
                "aqui você vê o nome e o que cada uma faz.",
            style = MaterialTheme.typography.bodyMedium,
        )
        HandoffTool.ALL.forEach { tool ->
            Card(Modifier.fillMaxWidth()) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(tool.icon, style = MaterialTheme.typography.headlineMedium)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(tool.title, fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.titleMedium)
                        Text(tool.description, style = MaterialTheme.typography.bodyMedium)
                        Spacer(Modifier.size(4.dp))
                        Text("Como funciona: ${tool.howItWorks}",
                            style = MaterialTheme.typography.bodySmall)
                    }
                    Spacer(Modifier.width(8.dp))
                    Switch(
                        checked = tool.id in enabled,
                        onCheckedChange = { scope.launch { settings.setToolEnabled(tool.id, it) } },
                    )
                }
            }
        }
    }
}

// ---- Helpers ----
private fun canOverlay(context: Context): Boolean =
    Build.VERSION.SDK_INT < Build.VERSION_CODES.M || AndroidSettings.canDrawOverlays(context)

private fun notificationsGranted(context: Context): Boolean =
    Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
        context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
        PackageManager.PERMISSION_GRANTED

private fun openOverlaySettings(context: Context) {
    context.startActivity(
        Intent(AndroidSettings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}

private fun openAccessibilitySettings(context: Context) {
    context.startActivity(
        Intent(AndroidSettings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}

private fun openUsageAccessSettings(context: Context) {
    context.startActivity(
        Intent(AndroidSettings.ACTION_USAGE_ACCESS_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}

private fun openAppNotificationSettings(context: Context) {
    val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        Intent(AndroidSettings.ACTION_APP_NOTIFICATION_SETTINGS)
            .putExtra(AndroidSettings.EXTRA_APP_PACKAGE, context.packageName)
    } else {
        Intent(AndroidSettings.ACTION_SETTINGS)
    }
    context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

private fun openBatterySettings(context: Context) {
    val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
        Intent(AndroidSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${context.packageName}"))
    } else {
        Intent(AndroidSettings.ACTION_SETTINGS)
    }
    context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

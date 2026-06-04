package com.firepot.ecossistema

import android.Manifest
import android.app.AppOpsManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.os.Process
import android.provider.Settings as AndroidSettings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
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
import androidx.compose.material3.TextButton
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
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.firepot.ecossistema.data.PcConfig
import com.firepot.ecossistema.data.Settings
import com.firepot.ecossistema.handoff.HandoffManager
import com.firepot.ecossistema.model.PcApp
import com.firepot.ecossistema.pairing.PairingManager
import com.firepot.ecossistema.service.HandoffAccessibilityService
import com.firepot.ecossistema.service.HandoffForegroundService
import com.firepot.ecossistema.tools.CustomTool
import com.firepot.ecossistema.tools.HandoffTool
import com.firepot.ecossistema.ui.theme.EcossistemaTheme
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.launch
import java.util.UUID

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
    var configExpanded by remember { mutableStateOf(false) }

    var serviceOn by remember { mutableStateOf(HandoffForegroundService.isRunning) }
    var recheck by remember { mutableIntStateOf(0) }
    var pareando by remember { mutableStateOf(false) }

    // Scanner de QR (proposta B): le o QR do painel do PC e fecha o pareamento.
    val scanLauncher = rememberLauncherForActivityResult(ScanContract()) { result ->
        val conteudo = result.contents
        if (conteudo == null) {
            Toast.makeText(context, "Pareamento cancelado", Toast.LENGTH_SHORT).show()
            return@rememberLauncherForActivityResult
        }
        val info = PairingManager.parse(conteudo)
        if (info == null) {
            Toast.makeText(context, "QR invalido (nao parece do Ecossistema)", Toast.LENGTH_LONG).show()
            return@rememberLauncherForActivityResult
        }
        pareando = true
        scope.launch {
            val r = PairingManager.pair(context, info)
            pareando = false
            if (r.isSuccess) {
                Toast.makeText(context, "Pareado com ${info.host}!", Toast.LENGTH_LONG).show()
                recheck++
            } else {
                Toast.makeText(
                    context, "Falha: ${r.exceptionOrNull()?.message ?: "erro"}", Toast.LENGTH_LONG,
                ).show()
            }
        }
    }
    var status by remember { mutableStateOf(ConnStatus.UNCONFIGURED) }
    var stHost by remember { mutableStateOf("") }
    var stUser by remember { mutableStateOf("") }

    // Recalcula o estado das permissões toda vez que o usuário volta pro app.
    var permsTick by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { permsTick++ }
    val overlayOk = remember(permsTick) { canOverlay(context) }
    val accOk = remember(permsTick) { accessibilityEnabled(context) }
    val notifOk = remember(permsTick) { notificationsGranted(context) }
    val usageOk = remember(permsTick) { usageAccessGranted(context) }
    val batteryOk = remember(permsTick) { batteryIgnored(context) }

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

        // 1b) Parear por QR (recomendado) — zero IP/chave colada (proposta B).
        Button(
            onClick = {
                scanLauncher.launch(
                    ScanOptions().apply {
                        setPrompt("Aponte para o QR no painel do PC")
                        setBeepEnabled(false)
                        setOrientationLocked(false)
                    },
                )
            },
            enabled = !pareando,
            modifier = Modifier.fillMaxWidth(),
        ) { Text(if (pareando) "Pareando…" else "Parear com QR") }

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
                                // Sem a isenção de bateria a Samsung mata o serviço
                                // (a bolha some e o canal cai). Nudge na 1ª vez.
                                if (!batteryIgnored(context)) {
                                    Toast.makeText(
                                        context,
                                        "Vai abrir \"Otimizar bateria?\" — toque em NÃO (não otimizar) " +
                                            "para o sistema não desligar a bolha.",
                                        Toast.LENGTH_LONG,
                                    ).show()
                                    openBatterySettings(context)
                                }
                            }
                        } else {
                            HandoffForegroundService.stop(context)
                            serviceOn = false
                        }
                    },
                )
            }
        }

        // 3) Conexão com o PC — colapsada por padrão
        HorizontalDivider()
        Row(
            Modifier.fillMaxWidth().clickable { configExpanded = !configExpanded },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Conexão com o PC", style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f))
            Text(if (configExpanded) "▾" else "▸", style = MaterialTheme.typography.titleMedium)
        }
        if (configExpanded) {
            OutlinedTextField(host, { host = it }, label = { Text("Host (IP LAN ou 100.x)") },
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
        }

        // 4) Permissões no rodapé
        HorizontalDivider()
        Text("Permissões", style = MaterialTheme.typography.titleMedium)
        Text("❗ = obrigatória para a bolha   ·   ✅ concedida   ·   ❌ falta",
            style = MaterialTheme.typography.bodySmall)
        PermissionRow("Sobreposição (overlay)", obrigatoria = true, granted = overlayOk,
            detail = "Faz a bolha aparecer sobre os outros apps.") { openOverlaySettings(context) }
        PermissionRow("Acessibilidade", obrigatoria = true, granted = accOk,
            detail = "Necessária para a ferramenta \"Link da tela\" ler a URL aberta.") {
            openAccessibilitySettings(context)
        }
        PermissionRow("Notificações", obrigatoria = false, granted = notifOk,
            detail = "Mostra a notificação fixa do serviço (recomendado).") {
            openAppNotificationSettings(context)
        }
        PermissionRow("Acesso de uso", obrigatoria = false, granted = usageOk,
            detail = "Opcional: ajuda a inferir o app em foco.") { openUsageAccessSettings(context) }
        PermissionRow("Ignorar otimização de bateria", obrigatoria = false, granted = batteryOk,
            detail = "Recomendado na Samsung: sem isso o sistema mata a bolha e o canal cai.") {
            openBatterySettings(context)
        }
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
            Text(
                when (granted) { true -> "✅"; false -> "❌"; else -> "•" },
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(nome, style = MaterialTheme.typography.titleSmall)
                    if (obrigatoria) {
                        Spacer(Modifier.width(6.dp))
                        Text("❗", style = MaterialTheme.typography.titleSmall)
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
    val customTools by settings.customTools.collectAsState(initial = emptyList())

    var apps by remember { mutableStateOf<List<PcApp>>(emptyList()) }
    var showPicker by remember { mutableStateOf(false) }
    var loadingApps by remember { mutableStateOf(false) }

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
            ToolCard(tool.icon, tool.title, tool.description, "Como funciona: ${tool.howItWorks}",
                checked = tool.id in enabled,
                onToggle = { scope.launch { settings.setToolEnabled(tool.id, it) } })
        }

        HorizontalDivider()
        Text("Apps do PC (personalizadas)", style = MaterialTheme.typography.titleLarge)
        Text("Crie um atalho que abre um app específico do seu PC pelo celular.",
            style = MaterialTheme.typography.bodyMedium)
        customTools.forEach { ct ->
            Card(Modifier.fillMaxWidth()) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(ct.nome.take(1).uppercase(), style = MaterialTheme.typography.headlineSmall)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(ct.nome, fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.titleMedium)
                        Text("Abre este app no PC.", style = MaterialTheme.typography.bodySmall)
                    }
                    Text("🗑", style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.clickable { scope.launch { settings.removeCustomTool(ct.id) } })
                    Spacer(Modifier.width(12.dp))
                    Switch(
                        checked = ct.id in enabled,
                        onCheckedChange = { scope.launch { settings.setToolEnabled(ct.id, it) } },
                    )
                }
            }
        }
        Button(
            onClick = {
                loadingApps = true
                scope.launch {
                    HandoffManager.listApps(context)
                        .onSuccess { apps = it; showPicker = true }
                        .onFailure {
                            Toast.makeText(context, "Falha ao listar apps: ${it.message}", Toast.LENGTH_LONG).show()
                        }
                    loadingApps = false
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text(if (loadingApps) "Buscando apps do PC…" else "➕ Adicionar app do PC") }
    }

    if (showPicker) {
        AppPickerDialog(apps, onDismiss = { showPicker = false }) { app ->
            scope.launch {
                settings.addCustomTool(CustomTool("app:${UUID.randomUUID()}", app.nome, app.caminho))
                Toast.makeText(context, "Adicionado: ${app.nome}", Toast.LENGTH_SHORT).show()
            }
            showPicker = false
        }
    }
}

@Composable
private fun ToolCard(
    icon: String, title: String, description: String, how: String,
    checked: Boolean, onToggle: (Boolean) -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(icon, style = MaterialTheme.typography.headlineMedium)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                Text(description, style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.size(4.dp))
                Text(how, style = MaterialTheme.typography.bodySmall)
            }
            Spacer(Modifier.width(8.dp))
            Switch(checked = checked, onCheckedChange = onToggle)
        }
    }
}

@Composable
private fun AppPickerDialog(apps: List<PcApp>, onDismiss: () -> Unit, onPick: (PcApp) -> Unit) {
    var query by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("Fechar") } },
        title = { Text("Escolha um app do PC") },
        text = {
            Column {
                OutlinedTextField(query, { query = it }, label = { Text("Filtrar") },
                    modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.size(8.dp))
                val filtered = apps.filter { it.nome.contains(query, ignoreCase = true) }
                LazyColumn(Modifier.heightIn(max = 380.dp)) {
                    items(filtered) { app ->
                        Text(
                            app.nome,
                            style = MaterialTheme.typography.bodyLarge,
                            modifier = Modifier.fillMaxWidth().clickable { onPick(app) }.padding(vertical = 10.dp),
                        )
                    }
                }
            }
        },
    )
}

// ---- Helpers ----
private fun canOverlay(context: Context): Boolean =
    Build.VERSION.SDK_INT < Build.VERSION_CODES.M || AndroidSettings.canDrawOverlays(context)

private fun notificationsGranted(context: Context): Boolean =
    Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
        context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
        PackageManager.PERMISSION_GRANTED

private fun accessibilityEnabled(context: Context): Boolean {
    val cn = ComponentName(context, HandoffAccessibilityService::class.java)
    val flat = cn.flattenToString()
    val short = cn.flattenToShortString()
    val s = AndroidSettings.Secure.getString(
        context.contentResolver, AndroidSettings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
    ) ?: return false
    return s.split(':').any { it.equals(flat, true) || it.equals(short, true) }
}

private fun usageAccessGranted(context: Context): Boolean = try {
    val aom = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
    val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        aom.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName)
    } else {
        @Suppress("DEPRECATION")
        aom.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName)
    }
    mode == AppOpsManager.MODE_ALLOWED
} catch (_: Exception) {
    false
}

private fun batteryIgnored(context: Context): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return true
    val pm = context.getSystemService(Context.POWER_SERVICE) as PowerManager
    return pm.isIgnoringBatteryOptimizations(context.packageName)
}

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

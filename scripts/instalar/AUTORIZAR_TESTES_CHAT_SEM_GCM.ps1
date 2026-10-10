# Opcao de menor atrito, autorizada explicitamente pelo proprietario.
# TROCA apenas a politica complementar do chat e sua aprovacao separada.
# O controle manual legado e o hook principal permanecem intactos.
# RISCO: delega verificacoes remotas de PR/workflow ao job hospedado do GitHub.
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$source = Join-Path $root 'remote_tests\chat-control-functions.ps1'
$policy = Join-Path $env:USERPROFILE 'auren-remote\policy'
$target = Join-Path $policy 'chat-control-functions.ps1'
$approvalFile = Join-Path $policy 'chat-control-approval.json'
$hook = Join-Path $policy 'before-job.ps1'
$backup = Join-Path $policy 'chat-control-functions.pre-offline.bak'
$approvalBackup = Join-Path $policy 'chat-control-approval.pre-offline.bak'
$blob = '52abfd109c06cdc458727337579984d91da879bc'

foreach ($item in @($source, $target, $approvalFile, $hook)) {
    if (-not (Test-Path -LiteralPath $item -PathType Leaf)) {
        throw "Arquivo nao encontrado: $item"
    }
}
$installed = [IO.File]::ReadAllText($target)
$replacement = [IO.File]::ReadAllText($source)
$hookText = [IO.File]::ReadAllText($hook)
$approval = Get-Content -LiteralPath $approvalFile -Raw | ConvertFrom-Json

if ($approval.enabled -ne $true -or $approval.workflow_blob -cne $blob -or
    -not $hookText.Contains('Test-ChatControlRequest')) {
    throw 'Aprovacao e hook original nao conferem; nenhuma alteracao.'
}
$offlineMarker = 'offline_hosted_validation'
if ($installed.Contains($offlineMarker) -or $approval.offline_hosted_validation -eq $true) {
    if ($installed.Contains($offlineMarker) -and $approval.offline_hosted_validation -eq $true) {
        Write-Output 'Autorizacao sem GCM ja instalada.'
        exit 0
    }
    throw 'Instalacao incompleta detectada; nao sobrescrever.'
}
if (-not $installed.Contains('function Test-ChatControlRequest') -or
    -not $installed.Contains('Invoke-BoundedLocalTool') -or
    -not $installed.Contains($blob) -or
    -not $replacement.Contains('function Test-ChatControlRequest') -or
    -not $replacement.Contains($offlineMarker) -or
    $replacement.Contains('Invoke-BoundedLocalTool') -or
    -not $replacement.Contains($blob) -or
    -not $replacement.Contains('Runner elevado ou parada de emergencia ativa.')) {
    throw 'Politica atual inesperada; nenhuma alteracao.'
}

$parseErrors = $null
$tokens = $null
[void][System.Management.Automation.Language.Parser]::ParseInput(
    $replacement, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors -and @($parseErrors).Count -gt 0) {
    throw 'Erro de sintaxe na politica atualizada.'
}
if ((Test-Path -LiteralPath $backup -PathType Leaf) -or
    (Test-Path -LiteralPath $approvalBackup -PathType Leaf)) {
    throw 'Backups desta operacao ja existem; nao sobrescrever.'
}

$approval | Add-Member -MemberType NoteProperty -Name $offlineMarker -Value $true
$approvalUpdated = $approval | ConvertTo-Json -Compress -Depth 6
Copy-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
try {
    Copy-Item -LiteralPath $approvalFile -Destination $approvalBackup -ErrorAction Stop
    [IO.File]::WriteAllText($target, $replacement, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($approvalFile, $approvalUpdated, [Text.UTF8Encoding]::new($false))
} catch {
    Copy-Item -LiteralPath $backup -Destination $target -Force
    if (Test-Path -LiteralPath $approvalBackup -PathType Leaf) {
        Copy-Item -LiteralPath $approvalBackup -Destination $approvalFile -Force
    }
    throw
}
Write-Output 'Autorizacao offline instalada. Sem GCM. Hook e controle manual preservados.'

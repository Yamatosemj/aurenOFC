# Ajuste pontual da consulta Git/GCM usada no pre-job do runner.
# NAO muda o hook principal, aprovacoes, workflows ou as politicas de permissao.
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$source = Join-Path $root 'remote_tests\chat-control-functions.ps1'
$policy = Join-Path $env:USERPROFILE 'auren-remote\policy'
$target = Join-Path $policy 'chat-control-functions.ps1'
$hook = Join-Path $policy 'before-job.ps1'
$approvalFile = Join-Path $policy 'chat-control-approval.json'
$backup = Join-Path $policy 'chat-control-functions.pre-gcm-cwd.bak'
$blob = '90e3e3070f8b977bc328dc6ad72b112407ffeb3d'

foreach ($file in @($source, $target, $hook, $approvalFile)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Arquivo esperado ausente: $file"
    }
}
$approval = Get-Content -LiteralPath $approvalFile -Raw | ConvertFrom-Json
if ($approval.enabled -ne $true -or $approval.workflow_blob -cne $blob) {
    throw 'Aprovacao do workflow nao coincide com a revisao imutavel.'
}
$hookSource = [IO.File]::ReadAllText($hook)
if (-not $hookSource.Contains('Test-ChatControlRequest')) {
    throw 'O hook principal nao tem o controle do chat.'
}

$prior = [IO.File]::ReadAllText($target)
$replacement = [IO.File]::ReadAllText($source)
$marker = "credential.interactive=never credential fill"
$changeMarker = '$gitArgs = ' + "'-C "
$markers = @('function Test-ChatControlRequest', 'Runner elevado ou parada de emergencia ativa.',
    '90e3e3070f8b977bc328dc6ad72b112407ffeb3d', $marker)
foreach ($signature in $markers) {
    if (-not $prior.Contains($signature) -or -not $replacement.Contains($signature)) {
        throw 'Politica instalada nao corresponde a versao esperada; parada segura.'
    }
}
if ($prior.Contains($changeMarker)) {
    Write-Output 'Ajuste de credencial ja instalado. Nenhuma alteracao.'
    exit 0
}
if (-not $replacement.Contains($changeMarker)) {
    throw 'Versao corrigida do repositorio ainda nao disponivel.'
}
$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseInput(
    $replacement, [ref]$tokens, [ref]$errors
)
if ($errors -and @($errors).Count -gt 0) {
    throw 'Codigo corrigido nao passou na verificacao de sintaxe.'
}
if (Test-Path -LiteralPath $backup -PathType Leaf) {
    throw 'Backup de tentativa anterior existe, nao sobrescrever.'
}

Copy-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
try {
    [IO.File]::WriteAllText($target, $replacement, [Text.UTF8Encoding]::new($false))
} catch {
    Copy-Item -LiteralPath $backup -Destination $target -Force
    throw
}
Write-Output 'Consulta Git/GCM ajustada ao perfil Windows, com backup e permissoes preservadas.'

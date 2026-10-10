# Diagnostico pontual: marca apenas qual etapa da verificacao falha no Windows.
# NAO altera o workflow autorizado nem as permissoes de execucao.
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$origin = Join-Path $root 'remote_tests\chat-control-functions.ps1'
$policy = Join-Path $env:USERPROFILE 'auren-remote\policy'
$target = Join-Path $policy 'chat-control-functions.ps1'
$approvalFile = Join-Path $policy 'chat-control-approval.json'
$hook = Join-Path $policy 'before-job.ps1'
$backup = Join-Path $policy 'chat-control-functions.pre-stage-diagnostic.bak'
$expectedBlob = '90e3e3070f8b977bc328dc6ad72b112407ffeb3d'

foreach ($file in @($origin, $target, $approvalFile, $hook)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Instalacao incompleta: $file"
    }
}
$approval = Get-Content -LiteralPath $approvalFile -Raw | ConvertFrom-Json
if ($approval.enabled -ne $true -or $approval.workflow_blob -cne $expectedBlob) {
    throw 'Aprovacao existente inesperada; nao alterar.'
}
$hookSource = [IO.File]::ReadAllText($hook)
if (-not $hookSource.Contains('Test-ChatControlRequest')) {
    throw 'Hook Windows nao contem a protecao do chat.'
}

$current = [IO.File]::ReadAllText($target)
$replacement = [IO.File]::ReadAllText($origin)
$required = @('function Test-ChatControlRequest', 'Invoke-BoundedLocalTool',
              'Stop', '90e3e3070f8b977bc328dc6ad72b112407ffeb3d')
foreach ($signature in $required) {
    if (-not $current.Contains($signature) -or -not $replacement.Contains($signature)) {
        throw 'Fonte local divergente da politica autorizada; nenhuma mudanca.'
    }
}
if ($current.Contains('Etapa consultar conteudo SHA do workflow falhou no runner.')) {
    Write-Output 'Diagnostico das etapas ja instalado.'
    exit 0
}
if (-not $replacement.Contains('Etapa consultar conteudo SHA do workflow falhou no runner.')) {
    throw 'Fonte atualizada ainda nao contem o diagnostico esperado.'
}

$errors = $null
$tokens = $null
[void][System.Management.Automation.Language.Parser]::ParseInput(
    $replacement, [ref]$tokens, [ref]$errors
)
if ($errors -and @($errors).Count -gt 0) {
    throw 'A nova fonte nao passou na verificacao de sintaxe PowerShell.'
}
if (Test-Path -LiteralPath $backup -PathType Leaf) {
    throw 'Backup de diagnostico ja existe; nao sobrescrever.'
}

Copy-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
try {
    [IO.File]::WriteAllText($target, $replacement, [Text.UTF8Encoding]::new($false))
} catch {
    Copy-Item -LiteralPath $backup -Destination $target -Force
    throw
}
Write-Output 'Diagnostico instalado: protecoes e aprovacoes preservadas.'

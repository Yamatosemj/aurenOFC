# Atualiza a autorizacao offline do chat APENAS para workflow com resumo ASCII.
# Requer consentimento local. Nao altera o hook principal nem permissao legada.
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$source = Join-Path $root 'remote_tests\chat-control-functions.ps1'
$policy = Join-Path $env:USERPROFILE 'auren-remote\policy'
$target = Join-Path $policy 'chat-control-functions.ps1'
$approvalFile = Join-Path $policy 'chat-control-approval.json'
$hook = Join-Path $policy 'before-job.ps1'
$backup = Join-Path $policy 'chat-control-functions.pre-ascii-workflow.bak'
$approvalBackup = Join-Path $policy 'chat-control-approval.pre-ascii-workflow.bak'
$oldBlob = '90e3e3070f8b977bc328dc6ad72b112407ffeb3d'
$newBlob = '52abfd109c06cdc458727337579984d91da879bc'

foreach ($file in @($source, $target, $approvalFile, $hook)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Arquivo esperado ausente: $file"
    }
}
$installed = [IO.File]::ReadAllText($target)
$updated = [IO.File]::ReadAllText($source)
$hookText = [IO.File]::ReadAllText($hook)
$approval = Get-Content -LiteralPath $approvalFile -Raw | ConvertFrom-Json
if (-not $hookText.Contains('Test-ChatControlRequest')) {
    throw 'Hook local do chat inesperado; nenhuma alteracao.'
}
if ($approval.workflow_blob -ceq $newBlob -and
    $approval.offline_hosted_validation -eq $true -and
    $installed.Contains($newBlob) -and
    -not $installed.Contains('Invoke-BoundedLocalTool')) {
    Write-Output 'Atualizacao de workflow ASCII ja instalada.'
    exit 0
}
if ($approval.enabled -ne $true -or $approval.offline_hosted_validation -ne $true -or
    $approval.workflow_blob -cne $oldBlob -or
    -not $installed.Contains('function Test-ChatControlRequest') -or
    -not $installed.Contains($oldBlob) -or
    -not $installed.Contains('offline_hosted_validation') -or
    $installed.Contains('Invoke-BoundedLocalTool') -or
    -not $updated.Contains('function Test-ChatControlRequest') -or
    -not $updated.Contains($newBlob) -or
    -not $updated.Contains('offline_hosted_validation') -or
    $updated.Contains('Invoke-BoundedLocalTool') -or
    -not $updated.Contains('Runner elevado ou parada de emergencia ativa.')) {
    throw 'Politica atual diverge da autorizacao offline anterior; nenhuma alteracao.'
}

$errors = $null
$tokens = $null
[void][System.Management.Automation.Language.Parser]::ParseInput(
    $updated, [ref]$tokens, [ref]$errors
)
if ($errors -and @($errors).Count -gt 0) {
    throw 'Politica atualizada nao passou na validacao sintatica.'
}
if ((Test-Path -LiteralPath $backup -PathType Leaf) -or
    (Test-Path -LiteralPath $approvalBackup -PathType Leaf)) {
    throw 'Backup desta migracao ja existe; nao sobrescrever.'
}

$approval.workflow_blob = $newBlob
$approvalText = $approval | ConvertTo-Json -Compress -Depth 6
Copy-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
try {
    Copy-Item -LiteralPath $approvalFile -Destination $approvalBackup -ErrorAction Stop
    [IO.File]::WriteAllText($target, $updated, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($approvalFile, $approvalText, [Text.UTF8Encoding]::new($false))
} catch {
    Copy-Item -LiteralPath $backup -Destination $target -Force
    if (Test-Path -LiteralPath $approvalBackup -PathType Leaf) {
        Copy-Item -LiteralPath $approvalBackup -Destination $approvalFile -Force
    }
    throw
}
Write-Output 'Workflow ASCII autorizado no Windows. Politica offline e backups preservados.'

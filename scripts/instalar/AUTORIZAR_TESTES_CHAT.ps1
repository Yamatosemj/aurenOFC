# Executar APENAS uma vez no Windows, depois de atualizar a main do Auren.
# Acrescenta a politica restrita de testes via chat; preserva o controle manual.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$source = Join-Path $root 'remote_tests\chat-control-functions.ps1'
$policy = Join-Path $env:USERPROFILE 'auren-remote\policy'
$hook = Join-Path $policy 'before-job.ps1'
$legacyFunctions = Join-Path $policy 'remote-control-functions.ps1'
$legacyApproval = Join-Path $policy 'control-approval.json'
$chatFunctions = Join-Path $policy 'chat-control-functions.ps1'
$chatApproval = Join-Path $policy 'chat-control-approval.json'
$backup = Join-Path $policy 'before-job.pre-chat.bak'
$approvedBlob = '90e3e3070f8b977bc328dc6ad72b112407ffeb3d'

foreach ($file in @($source, $hook, $legacyFunctions, $legacyApproval)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Configuracao ausente: $file"
    }
}

# So instalar a versao exata dos controles revisados.
$installed = [IO.File]::ReadAllText($hook)
if ($installed.Contains('Test-ChatControlRequest')) {
    if (-not (Test-Path -LiteralPath $chatApproval -PathType Leaf) -or
        -not (Test-Path -LiteralPath $chatFunctions -PathType Leaf)) {
        throw 'Instalacao anterior incompleta; nao sobrescrever automaticamente.'
    }
    $current = Get-Content -LiteralPath $chatApproval -Raw | ConvertFrom-Json
    if ($current.enabled -ne $true -or $current.workflow_blob -cne $approvedBlob) {
        throw 'Aprovacao existente diverge da revisada; nao sobrescrever.'
    }
    Write-Output 'Testes por chat: configuracao ja instalada.'
    exit 0
}

$oldBlock = @'
    Test-RemoteControlRequest -Context $context -Event $event -Approval $approval -Elevated $elevated -Stopped $stopped
    if ($event.inputs.operacao -ceq 'testar_pr') {
        $resolved = Get-ResolvedReviewedPrSha -RunId $env:GITHUB_RUN_ID -Attempt $env:GITHUB_RUN_ATTEMPT -PrNumber $event.inputs.numero_pr
        Test-RemoteControlRequest -Context $context -Event $event -Approval $approval -Elevated $elevated -Stopped $stopped -ResolvedPrSha $resolved
    }
'@

$newBlock = @'
    if ($context.event_name -ceq 'issue_comment') {
        . (Join-Path $PSScriptRoot 'chat-control-functions.ps1')
        $chatApproval = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'chat-control-approval.json') -Raw | ConvertFrom-Json
        Test-ChatControlRequest -Context $context -Event $event -ChatApproval $chatApproval -Elevated $elevated -Stopped $stopped -RunId $env:GITHUB_RUN_ID -Attempt $env:GITHUB_RUN_ATTEMPT
    } else {
        Test-RemoteControlRequest -Context $context -Event $event -Approval $approval -Elevated $elevated -Stopped $stopped
        if ($event.inputs.operacao -ceq 'testar_pr') {
            $resolved = Get-ResolvedReviewedPrSha -RunId $env:GITHUB_RUN_ID -Attempt $env:GITHUB_RUN_ATTEMPT -PrNumber $event.inputs.numero_pr
            Test-RemoteControlRequest -Context $context -Event $event -Approval $approval -Elevated $elevated -Stopped $stopped -ResolvedPrSha $resolved
        }
    }
'@


$oldBlock = $oldBlock.TrimEnd()
$newBlock = $newBlock.TrimEnd()

$normalized = $installed.Replace("`r`n", "`n")
if (-not $normalized.Contains($oldBlock)) {
    throw 'Hook local diferente do revisado; nenhuma alteracao feita.'
}
$revised = $normalized.Replace($oldBlock, $newBlock)
if ($revised -eq $normalized -or $revised.Contains('Test-RemoteControlRequest') -eq $false) {
    throw 'Nao foi possivel montar a alteracao sem perder o controle antigo.'
}
$revised = $revised.Replace(
    'Politica local aprovada: somente controle manual fixo, proprietario, SHA revisado e privilegios limitados.',
    'Politica local aprovada: controle especifico, proprietario e privilegios limitados.'
)

# Validar sintaxe PowerShell antes de escrever no hook ativo.
$parseErrors = $null
$tokens = $null
[void][System.Management.Automation.Language.Parser]::ParseInput(
    $revised, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors -and @($parseErrors).Count -gt 0) {
    throw 'Novo hook nao passou na validacao sintatica do PowerShell.'
}
$chatSource = [IO.File]::ReadAllText($source)
$parseErrors = $null
$tokens = $null
[void][System.Management.Automation.Language.Parser]::ParseInput(
    $chatSource, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors -and @($parseErrors).Count -gt 0) {
    throw 'Politica complementar nao passou na validacao sintatica.'
}
if (Test-Path -LiteralPath $backup -PathType Leaf) {
    throw 'Backup de uma instalacao anterior ja existe; conferir antes de editar.'
}

# Copia de seguranca + escrita do hook por ultimo: a versao antiga fica valida
# ate os dois arquivos de suporte estarem preparados.
Copy-Item -LiteralPath $hook -Destination $backup -ErrorAction Stop
try {
    [IO.File]::WriteAllText($chatFunctions, $chatSource, [Text.UTF8Encoding]::new($false))
    $approvalText = "{`"enabled`":true,`"workflow_blob`":`"$approvedBlob`"}"
    [IO.File]::WriteAllText($chatApproval, $approvalText, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($hook, $revised.Replace("`n", "`r`n"), [Text.UTF8Encoding]::new($false))
} catch {
    Copy-Item -LiteralPath $backup -Destination $hook -Force
    throw
}
Write-Output 'Configuracao concluida. O fluxo manual antigo foi preservado.'
Write-Output 'O novo fluxo aceita somente pedidos de pytest assinados pelo proprietario e workflow imutavel.'
Write-Output 'Nao e necessario abrir o GitHub nem preencher formulario por teste.'

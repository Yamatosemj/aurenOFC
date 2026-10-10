# Auren: politica complementar de testes solicitados pelo chat.
# Este arquivo e instalado uma vez no Windows ao lado de before-job.ps1.
# NAO altera nem desativa Test-RemoteControlRequest (fluxo manual legado).
$ErrorActionPreference = 'Stop'

function Test-ChatControlRequest {
    param($Context, $Event, $ChatApproval, [bool]$Elevated, [bool]$Stopped,
          [string]$RunId, [string]$Attempt)

    $owner = 'Yamatosemj'
    $repository = 'Yamatosemj/aurenOFC'
    $workflow = 'Yamatosemj/aurenOFC/.github/workflows/auren-chat-tests.yml@refs/heads/main'
    $workflowBlob = '90e3e3070f8b977bc328dc6ad72b112407ffeb3d'

    if ($Elevated -or $Stopped) { throw 'Runner elevado ou parada de emergencia ativa.' }
    if ($ChatApproval.enabled -ne $true -or $ChatApproval.workflow_blob -cne $workflowBlob) {
        throw 'Workflow do chat nao autorizado pelo proprietario local.'
    }
    if ($Context.repository -cne $repository -or
        $Context.event_name -cne 'issue_comment' -or
        $Context.ref -cne 'refs/heads/main' -or
        $Context.workflow_ref -cne $workflow -or
        $Context.actor -cne $owner -or
        $Context.triggering_actor -cne $owner -or
        $Context.sha -cnotmatch '^[a-f0-9]{40}$' -or
        $Context.workflow_sha -cne $Context.sha -or
        $env:GITHUB_JOB -cne 'executar' -or
        $RunId -cnotmatch '^[1-9][0-9]*$' -or $Attempt -cne '1') {
        throw 'Workflow, contexto ou tentativa do chat nao autorizado.'
    }
    if ($Event.action -cne 'created' -or
        $Event.repository.private -ne $true -or
        $Event.repository.full_name -cne $repository -or
        $Event.repository.owner.login -cne $owner -or
        $Event.sender.login -cne $owner -or
        $Event.comment.user.login -cne $owner -or
        -not $Event.issue.pull_request) {
        throw 'Comentario nao autorizado ou nao pertence a uma PR.'
    }

    $prNumber = [string]$Event.issue.number
    $body = [string]$Event.comment.body
    if ($prNumber -cnotmatch '^[1-9][0-9]{0,5}$' -or
        $body -cnotmatch '\AAUREN_TESTE_V1 pytest ([a-f0-9]{40})\z') {
        throw 'Comando ou numero de PR invalido.'
    }
    $prSha = $Matches[1]

    # Usa a verificacao limitada e sem prompts do controle preexistente.
    # Nao registra nem imprime tokens ou respostas sensiveis no log.
    $credential = Invoke-BoundedLocalTool -Executable 'C:\Program Files\Git\cmd\git.exe' `
        -Arguments '-c credential.interactive=never credential fill' -InputText "protocol=https`nhost=github.com`n`n"
    $line = $credential -split "`n" | Where-Object { $_ -like 'password=*' } | Select-Object -First 1
    if (-not $line) { throw 'Credencial nao interativa indisponivel.' }
    $token = $line.Substring(9).TrimEnd("`r")
    $gh = Join-Path $env:USERPROFILE 'auren-remote\gh\bin\gh.exe'
    if (-not (Test-Path -LiteralPath $gh -PathType Leaf)) { throw 'CLI de verificacao nao instalada.' }

    # A main pode evoluir: autorizamos SOMENTE o conteudo imutavel do workflow
    # revisado (blob Git), mesmo que o commit da main tenha mudado.
    $path = "repos/$repository/contents/.github/workflows/auren-chat-tests.yml?ref=$($Context.sha)"
    $observedBlob = Invoke-BoundedLocalTool -Executable $gh -Token $token `
        -Arguments "api $path --jq .sha"
    if ($observedBlob.Trim() -cne $workflowBlob) {
        throw 'Workflow foi modificado desde a aprovacao local.'
    }

    $prJson = Invoke-BoundedLocalTool -Executable $gh -Token $token `
        -Arguments "api repos/$repository/pulls/$prNumber"
    $pr = $prJson | ConvertFrom-Json
    if ($pr.number -ne [int]$prNumber -or $pr.state -cne 'open' -or $pr.draft -or
        $pr.base.ref -cne 'main' -or $pr.base.repo.full_name -cne $repository -or
        $pr.head.repo.full_name -cne $repository -or $pr.head.sha -cne $prSha) {
        throw 'PR fechada, de fork ou alterada apos aprovacao.'
    }

    $jobsJson = Invoke-BoundedLocalTool -Executable $gh -Token $token `
        -Arguments "api repos/$repository/actions/runs/$RunId/attempts/$Attempt/jobs?per_page=100"
    $jobs = @((($jobsJson | ConvertFrom-Json).jobs))
    $validation = @($jobs | Where-Object { $_.name -ceq 'validar' -and $_.conclusion -ceq 'success' })
    if ($validation.Count -ne 1) {
        throw 'Validacao hospedada nao confirmada.'
    }
    Write-Output 'Politica do chat aprovada: workflow fixo, PR interna, SHA exato, pytest sem API e usuario nao elevado.'
}

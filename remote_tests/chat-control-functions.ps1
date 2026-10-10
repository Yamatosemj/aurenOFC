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
    if ($ChatApproval.enabled -ne $true -or
        $ChatApproval.workflow_blob -cne $workflowBlob -or
        $ChatApproval.offline_hosted_validation -ne $true) {
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
    if ($prNumber -cnotmatch '^[1-9][0-9]{0,5}$') {
        throw 'Numero da PR invalido.'
    }
    if ($body -cmatch '\AAUREN_TESTE_V1 pytest ([a-f0-9]{40})\z') {
        $prSha = $Matches[1]
    } else {
        throw 'Comando de teste invalido.'
    }

    # RISCO EXPLICITO ACEITO PELO PROPRIETARIO:
    # O job 'validar' do workflow fixo confere o estado da PR na API usando o
    # token efemero do GitHub antes de agendar 'executar'. Aqui nao existe
    # consulta de credenciais/API: confiamos no workflow de main e nos dados
    # de evento fornecidos pelo runner. Se alguem alterar esse workflow em main
    # ou comprometer a conta do proprietario, a protecao local nao detecta.
    # Mantemos evento, ator, repo privado, PR, SHA/commit do pedido, tentativa,
    # runner nao elevado e parada de emergencia.
    Write-Output 'Politica do chat aprovada (offline): proprietario, PR interna, commit declarado, pytest e usuario nao elevado.'
}

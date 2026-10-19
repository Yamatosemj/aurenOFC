"""Known terminal failures: no automated retry can fix these safely."""
STOP_MESSAGES = {
    "permission_denied": "A permissão para esta ação foi negada. Interrompi a tarefa sem repetir a ação.",
    "unknown_tool": "A ferramenta solicitada não está disponível nesta versão. A tarefa não foi concluída.",
    "not_implemented": "Esta capacidade ainda não está implementada. A tarefa não foi concluída.",
    "application_not_found": "Não encontrei o programa no Windows. Informe o nome instalado ou o caminho completo.",
    "application_search_timeout": "A busca do programa excedeu o tempo esperado. Informe o caminho completo para uma nova tentativa.",
    "application_access_denied": "O Windows negou acesso ao programa. Interrompi sem tentar contornar a restrição.",
    "application_launch_failed": "Não confirmei a abertura do programa. Interrompi sem repetir uma operação de resultado incerto.",
}

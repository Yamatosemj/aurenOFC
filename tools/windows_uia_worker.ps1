$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch {}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Normalize-Text([string]$Text) {
    if ($null -eq $Text) { return '' }
    try {
        $formD = $Text.Normalize([System.Text.NormalizationForm]::FormD)
        $semAcentos = [System.Text.RegularExpressions.Regex]::Replace($formD, '\p{Mn}', '')
        return [System.Text.RegularExpressions.Regex]::Replace($semAcentos.ToLowerInvariant(), '[^\p{L}\p{N}]+', ' ').Trim()
    } catch {
        return ($Text.ToLowerInvariant()).Trim()
    }
}

function Safe-String($Value) {
    if ($null -eq $Value) { return '' }
    try { return [string]$Value } catch { return '' }
}

function Get-ControlTypeName($Element) {
    try {
        $programmatic = Safe-String($Element.Current.ControlType.ProgrammaticName)
        if ($programmatic -match '\.([^\.]+)$') { return $Matches[1] }
        return $programmatic
    } catch { return '' }
}

function Get-PatternNames($Element) {
    # Mantemos a inspeção inicial enxuta. Padrões caros como TextPattern/Scroll
    # não são necessários para localizar os controles básicos e podem provocar
    # chamadas lentas em alguns provedores de UI. Eles ficam fora do inventário
    # inicial e podem ser adicionados futuramente em operações específicas.
    $patterns = [System.Collections.Generic.List[string]]::new()
    $known = @(
        @('Invoke', [System.Windows.Automation.InvokePattern]::Pattern),
        @('Value', [System.Windows.Automation.ValuePattern]::Pattern),
        @('Toggle', [System.Windows.Automation.TogglePattern]::Pattern),
        @('SelectionItem', [System.Windows.Automation.SelectionItemPattern]::Pattern),
        @('ExpandCollapse', [System.Windows.Automation.ExpandCollapsePattern]::Pattern)
    )
    foreach ($item in $known) {
        try {
            $null = $Element.GetCurrentPattern($item[1])
            $patterns.Add([string]$item[0])
        } catch {}
    }
    return $patterns.ToArray()
}

function Get-PatternState($Element, $PatternNames) {
    $states = New-Object System.Collections.Generic.List[string]
    if ($PatternNames -contains 'Toggle') {
        try {
            $pattern = $Element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
            $states.Add('toggle=' + (Safe-String $pattern.Current.ToggleState))
        } catch {}
    }
    if ($PatternNames -contains 'SelectionItem') {
        try {
            $pattern = $Element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
            $states.Add('selected=' + ([bool]$pattern.Current.IsSelected))
        } catch {}
    }
    if ($PatternNames -contains 'ExpandCollapse') {
        try {
            $pattern = $Element.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
            $states.Add('expand=' + (Safe-String $pattern.Current.ExpandCollapseState))
        } catch {}
    }
    return ($states -join '; ')
}

function Get-ElementText($Element, $ControlType, $PatternNames, [bool]$IsPassword) {
    if ($IsPassword) { return '' }

    # Para controles de edição, ValuePattern é a fonte de texto confiável.
    # Evitamos TextPattern durante a enumeração geral para não forçar provedores
    # mais pesados em toda a árvore.
    if ($PatternNames -contains 'Value') {
        try {
            $pattern = $Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            $value = Safe-String $pattern.Current.Value
            if ($value) { return $value }
        } catch {}
    }

    # O Name de Text/Status/Buttons normalmente já expõe o texto útil pela UIA.
    if ($ControlType -in @('Text', 'Button', 'CheckBox', 'ListItem', 'MenuItem', 'TabItem')) {
        try {
            $name = Safe-String $Element.Current.Name
            if ($name) { return $name }
        } catch {}
    }
    return ''
}

function Get-ElementInfo($Element) {
    try { $name = Safe-String $Element.Current.Name } catch { $name = '' }
    try { $automationId = Safe-String $Element.Current.AutomationId } catch { $automationId = '' }
    try { $className = Safe-String $Element.Current.ClassName } catch { $className = '' }
    try { $helpText = Safe-String $Element.Current.HelpText } catch { $helpText = '' }
    try { $enabled = [bool]$Element.Current.IsEnabled } catch { $enabled = $false }
    try { $offscreen = [bool]$Element.Current.IsOffscreen } catch { $offscreen = $false }
    try { $isPassword = [bool]$Element.Current.IsPassword } catch { $isPassword = $false }
    $controlType = Get-ControlTypeName $Element
    $patterns = Get-PatternNames $Element
    $text = Get-ElementText $Element $controlType $patterns $isPassword
    $state = Get-PatternState $Element $patterns
    [pscustomobject]@{
        Element = $Element
        Name = $name
        AutomationId = $automationId
        ClassName = $className
        HelpText = $helpText
        ControlType = $controlType
        Enabled = $enabled
        Offscreen = $offscreen
        IsPassword = $isPassword
        Patterns = @($patterns)
        Text = $text
        State = $state
    }
}

function Get-RootElement($Hwnd) {
    $handle = [IntPtr]::new([int64]$Hwnd)
    if ($handle -eq [IntPtr]::Zero) { throw 'Handle de janela invalido.' }
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
    if ($null -eq $root) { throw 'Nao consegui acessar a janela pela UI Automation.' }
    return $root
}

function Get-AllControls($Root) {
    # Em vez de uma única busca profunda, percorremos a árvore em BFS usando
    # apenas Children. Isso evita prender o processo em um provedor de UI ruim
    # e mantém um limite total para interfaces enormes.
    $fila = [System.Collections.Generic.Queue[object]]::new()
    $fila.Enqueue([pscustomobject]@{ Element = $Root; Depth = 0 })
    $items = [System.Collections.Generic.List[object]]::new()
    $visitados = 0
    $maxVisitados = 300
    $maxProfundidade = 14

    while ($fila.Count -gt 0 -and $visitados -lt $maxVisitados) {
        $entrada = $fila.Dequeue()
        $element = $entrada.Element
        $profundidade = [int]$entrada.Depth

        if ($null -eq $element) { continue }
        $visitados++

        try {
            $item = Get-ElementInfo $element
            $isControl = $false
            try { $isControl = [bool]$element.Current.IsControlElement } catch {}
            if ($isControl -and -not $item.Offscreen) {
                if ($item.Name -or $item.AutomationId -or $item.Text -or $item.IsPassword -or ($item.ControlType -in @('Button','Edit','Document','CheckBox','ComboBox','ListItem','MenuItem','TabItem','Text','List','Window'))) {
                    $items.Add($item)
                }
            }
        } catch {}

        if ($profundidade -ge $maxProfundidade) { continue }

        try {
            $children = $element.FindAll(
                [System.Windows.Automation.TreeScope]::Children,
                [System.Windows.Automation.Condition]::TrueCondition
            )
            for ($i = 0; $i -lt $children.Count; $i++) {
                if ($visitados + $fila.Count -ge $maxVisitados) { break }
                $filho = $children.Item($i)
                if ($null -ne $filho) { $fila.Enqueue([pscustomobject]@{ Element = $filho; Depth = ($profundidade + 1) }) }
            }
        } catch {}
    }

    return $items.ToArray()
}

function Get-MatchQuery([string]$Raw) {
    $norm = Normalize-Text $Raw
    $typeHint = ''
    $typeWords = @{
        'botao'='Button'; 'button'='Button';
        'campo'='Edit'; 'edit'='Edit'; 'textbox'='Edit';
        'checkbox'='CheckBox'; 'check'='CheckBox';
        'lista'='List'; 'list'='List';
        'item'='ListItem';
        'menu'='MenuItem'; 'menuitem'='MenuItem';
        'aba'='TabItem'; 'tab'='TabItem';
        'combo'='ComboBox'; 'combobox'='ComboBox'
    }
    $tokens = @($norm -split '\s+' | Where-Object { $_ })
    $kept = New-Object System.Collections.Generic.List[string]
    $keptLoose = New-Object System.Collections.Generic.List[string]
    foreach ($token in $tokens) {
        if ($typeWords.ContainsKey($token)) {
            $typeHint = $typeWords[$token]
            continue
        }
        $kept.Add($token)
        if ($token -notin @('de','do','da','dos','das','o','a','os','as','em','no','na','nos','nas')) {
            $keptLoose.Add($token)
        }
    }
    [pscustomobject]@{
        FullQuery = $norm
        RawQuery = (($kept -join ' ').Trim())
        LooseQuery = (($keptLoose -join ' ').Trim())
        TypeHint = $typeHint
    }
}

function Find-Controls($Items, [string]$Target, [string]$PreferPattern = '') {
    $query = Get-MatchQuery $Target
    $matches = [System.Collections.Generic.List[object]]::new()
    foreach ($item in $Items) {
        $name = Normalize-Text $item.Name
        $automationId = Normalize-Text $item.AutomationId
        $help = Normalize-Text $item.HelpText
        $text = Normalize-Text $item.Text
        $fullQuery = $query.FullQuery
        $rawQuery = $query.RawQuery
        $looseQuery = $query.LooseQuery
        $score = -1

        # Primeiro considera o pedido completo, antes de remover palavras de tipo.
        # Assim "Campo de Teste" nao empata com "Senha de Teste".
        if ($fullQuery) {
            if ($name -eq $fullQuery) { $score = 120 }
            elseif ($automationId -eq $fullQuery) { $score = 115 }
            elseif ($name.Contains($fullQuery)) { $score = 100 }
            elseif ($automationId.Contains($fullQuery)) { $score = 95 }
            elseif ($help.Contains($fullQuery) -or $text.Contains($fullQuery)) { $score = 85 }
        }

        if ($rawQuery) {
            if ($name -eq $rawQuery) { $score = [Math]::Max($score, 105) }
            elseif ($automationId -eq $rawQuery) { $score = [Math]::Max($score, 100) }
            elseif ($name.Contains($rawQuery)) { $score = [Math]::Max($score, 85) }
            elseif ($automationId.Contains($rawQuery)) { $score = [Math]::Max($score, 80) }
            elseif ($help.Contains($rawQuery) -or $text.Contains($rawQuery)) { $score = [Math]::Max($score, 70) }
        }

        if ($looseQuery) {
            $nameTokens = @($name -split '\s+' | Where-Object { $_ })
            $looseTokens = @($looseQuery -split '\s+' | Where-Object { $_ })
            $tokensPresent = $true
            foreach ($token in $looseTokens) {
                if ($token -notin $nameTokens -and $token -notin @($automationId -split '\s+')) {
                    $tokensPresent = $false
                    break
                }
            }
            if ($tokensPresent -and $looseTokens.Count -gt 0) {
                $score = [Math]::Max($score, 72)
            }
            elseif ($score -lt 0 -and ($name.Contains($looseQuery) -or $automationId.Contains($looseQuery) -or $help.Contains($looseQuery) -or $text.Contains($looseQuery))) {
                $score = 60
            }
        }

        if ($query.TypeHint) {
            if ($item.ControlType -ne $query.TypeHint) {
                if ($score -ge 0) { $score -= 30 } else { $score = -1 }
            }
            elseif ($score -lt 0 -and -not $query.RawQuery -and -not $query.LooseQuery) {
                $score = 50
            }
        }

        if ($score -ge 0 -and $PreferPattern) {
            if ($item.Patterns -contains $PreferPattern) {
                $score += 25
            }
        }

        if ($score -ge 0) { $matches.Add([pscustomobject]@{ Score=$score; Item=$item }) }
    }
    return @($matches | Sort-Object -Property @{Expression='Score';Descending=$true})
}

function Format-Item($Item, [int]$Index) {
    $name = if ($Item.Name) { $Item.Name } else { '[sem nome]' }
    $id = if ($Item.AutomationId) { $Item.AutomationId } else { '[sem AutomationId]' }
    $text = if ($Item.Text) { $Item.Text -replace '\r?\n',' ' } else { '' }
    if ($text.Length -gt 240) { $text = $text.Substring(0,240) + '...' }
    $valor = ''
    # Campos de senha nunca tem o valor lido/exibido. Controles editaveis
    # comuns que oferecem ValuePattern podem reportar o valor atual para que
    # a inspecao consiga confirmar mudancas reais de estado.
    if (-not $Item.IsPassword -and ($Item.Patterns -contains 'Value')) {
        try {
            $valuePattern = $Item.Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            $valor = Safe-String $valuePattern.Current.Value
        } catch {}
    }
    [pscustomobject]@{
        indice = $Index
        nome = $name
        automation_id = $id
        classe = $Item.ClassName
        tipo = $Item.ControlType
        habilitado = $Item.Enabled
        protegido = $Item.IsPassword
        padroes = @($Item.Patterns)
        estado = $Item.State
        texto = $text
        valor = $valor
    }
}


function Invoke-AurenOperation($payload) {
    try {
    $root = Get-RootElement ([string]$payload.hwnd)
    $items = Get-AllControls $root

    if ($payload.operacao -eq 'inspecionar') {
        $foco = [string]$payload.foco
        $max = [int]$payload.max_itens
        if ($max -lt 1) { $max = 1 }
        if ($max -gt 80) { $max = 80 }
        if ([string]::IsNullOrWhiteSpace($foco)) {
            $selecionados = @($items | Select-Object -First $max)
        } else {
            $matches = Find-Controls $items $foco
            $selecionados = @($matches | Select-Object -First $max | ForEach-Object { $_.Item })
        }
        $saida = @()
        $i = 1
        foreach ($item in $selecionados) { $saida += Format-Item $item $i; $i++ }
        $resultado = [pscustomobject]@{ ok=$true; operacao='inspecionar'; controles=@($saida); total=[int]$items.Count }
    } else {
        $target = [string]$payload.alvo
        if ([string]::IsNullOrWhiteSpace($target)) { throw 'Informe o nome, texto, AutomationId ou tipo do controle.' }
        $preferPattern = ''
        if ($payload.operacao -eq 'preencher') { $preferPattern = 'Value' }
        elseif ($payload.operacao -eq 'alternar') { $preferPattern = 'Toggle' }
        elseif ($payload.operacao -eq 'selecionar') { $preferPattern = 'SelectionItem' }
        elseif ($payload.operacao -eq 'clicar') { $preferPattern = 'Invoke' }
        $matches = Find-Controls $items $target $preferPattern
        if ($matches.Count -eq 0) { throw "Nao encontrei um controle correspondente a '$target'." }
        $indice = [int]$payload.indice
        if ($indice -lt 1 -or $indice -gt $matches.Count) { throw "Indice invalido para '$target'. Encontrei $($matches.Count) controle(s)." }

        if ($indice -eq 1 -and $matches.Count -gt 1) {
            $topScore = [int]$matches[0].Score
            $secondScore = [int]$matches[1].Score
            if ($topScore -eq $secondScore) {
                $candidatos = @($matches | Select-Object -First 5 | ForEach-Object {
                    $id = if ($_.Item.AutomationId) { $_.Item.AutomationId } else { '[sem AutomationId]' }
                    "$($_.Item.Name) [$($_.Item.ControlType); id=$id; protegido=$($_.Item.IsPassword); score=$($_.Score)]"
                })
                throw "Alvo ambiguo para '$target'. Dois ou mais controles empataram: $($candidatos -join ' | ')"
            }
        }

        $item = $matches[$indice - 1].Item
        if (-not $item.Enabled) { throw "O controle '$($item.Name)' esta desabilitado." }
        if ($item.Offscreen) { throw "O controle '$($item.Name)' esta fora da area visivel." }

        if ($payload.operacao -eq 'resolver') {
            $resultado = [pscustomobject]@{
                ok=$true; operacao='resolver'; nome=$item.Name; automation_id=$item.AutomationId;
                tipo=$item.ControlType; protegido=$item.IsPassword; score=[int]$matches[$indice - 1].Score;
                resultado="Controle resolvido: '$($item.Name)' ($($item.ControlType)); automation_id='$($item.AutomationId)'; protegido=$($item.IsPassword)."
            }
        } elseif ($payload.operacao -eq 'clicar') {
            if ($item.Patterns -contains 'Invoke') {
                $pattern = $item.Element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                $pattern.Invoke()
            } elseif ($item.Patterns -contains 'ExpandCollapse') {
                $pattern = $item.Element.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
                if ((Safe-String $pattern.Current.ExpandCollapseState) -eq 'Collapsed') { $pattern.Expand() } else { $pattern.Collapse() }
            } elseif ($item.Patterns -contains 'SelectionItem') {
                $pattern = $item.Element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
                $pattern.Select()
            } else {
                throw "O controle '$($item.Name)' nao oferece um padrao acionavel pela UI Automation."
            }
            Start-Sleep -Milliseconds 120
            $resultado = [pscustomobject]@{ ok=$true; operacao='clicar'; nome=$item.Name; tipo=$item.ControlType; resultado="Clique executado em '$($item.Name)' ($($item.ControlType))." }
        } elseif ($payload.operacao -eq 'preencher') {
            if ($item.IsPassword -and -not [bool]$payload.permitir_protegido) {
                throw "O controle '$($item.Name)' e protegido por IsPassword. O preenchimento de campos protegidos exige confirmacao explicita."
            }
            if (-not [bool]$item.IsPassword -and -not ($item.Patterns -contains 'Value')) {
                throw "O controle '$($item.Name)' nao oferece ValuePattern para preenchimento."
            }
            $textoDesejado = [string]$payload.texto
            $valuePattern = $null
            if (-not [bool]$item.IsPassword) {
                $valuePattern = $item.Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                if ([bool]$valuePattern.Current.IsReadOnly) { throw "O controle '$($item.Name)' e somente leitura." }
            }

            # O fluxo recomendado para entrada via UI Automation e dar foco
            # primeiro e depois usar ValuePattern.SetValue(). Alguns provedores
            # WPF falham ou permanecem com valor antigo quando SetValue e chamado
            # sem o foco do controle.
            try { $item.Element.SetFocus() } catch {}
            Start-Sleep -Milliseconds 100
            $setValueExecutado = $false
            $confirmado = ''

            # Campos protegidos (PasswordBox/IsPassword) nao usam SetValue como
            # evidencia de execucao. Alguns provedores podem aceitar SetValue sem
            # disparar os eventos normais do controle; nesses casos a entrada
            # fisica e a unica forma de preservar o comportamento real da interface.
            if (-not [bool]$item.IsPassword) {
                try {
                    $valuePattern = $item.Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                    $valuePattern.SetValue($textoDesejado)
                    $setValueExecutado = $true
                } catch {}
                Start-Sleep -Milliseconds 180

                # Releia o controle a partir da arvore atual para evitar depender de
                # um AutomationElement/pattern que possa estar com estado desatualizado.
                try {
                    $freshRoot = Get-RootElement ([string]$payload.hwnd)
                    $freshItems = Get-AllControls $freshRoot
                    $freshMatches = Find-Controls $freshItems $target 'Value'
                    if ($freshMatches.Count -gt 0) {
                        $freshItem = $freshMatches[0].Item
                        $freshPattern = $freshItem.Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                        $confirmado = Safe-String $freshPattern.Current.Value
                        $item = $freshItem
                        $valuePattern = $freshPattern
                    }
                } catch {
                    try { $confirmado = Safe-String $valuePattern.Current.Value } catch { $confirmado = '' }
                }
            }

            # Fallback para provedores que anunciam ValuePattern, mas nao
            # efetivam SetValue de forma confiavel. Para controles protegidos,
            # a entrada usa eventos de teclado reais via SendInput, mapeando
            # caracteres para teclas virtuais quando possivel e usando Unicode
            # apenas como fallback. Isso preserva KeyDown/WM_CHAR em WPF em vez
            # de depender exclusivamente de VK_PACKET.
            if ($item.IsPassword -or $confirmado -ne $textoDesejado) {
                try {
                    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class AurenUiWin32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
    [DllImport("user32.dll", SetLastError=true)] private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);
    [DllImport("user32.dll")] private static extern short VkKeyScanEx(char ch, IntPtr dwhkl);
    [DllImport("user32.dll")] private static extern IntPtr GetKeyboardLayout(uint idThread);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, IntPtr lpdwProcessId);
    [DllImport("user32.dll")] private static extern uint MapVirtualKeyEx(uint uCode, uint uMapType, IntPtr dwhkl);

    private const uint INPUT_KEYBOARD = 1;
    private const uint KEYEVENTF_KEYUP = 0x0002;
    private const uint KEYEVENTF_UNICODE = 0x0004;
    private const uint KEYEVENTF_SCANCODE = 0x0008;
    private const uint KEYEVENTF_EXTENDEDKEY = 0x0001;
    private const uint MAPVK_VK_TO_VSC_EX = 4;
    private const ushort VK_SHIFT = 0x10;
    private const ushort VK_CONTROL = 0x11;
    private const ushort VK_MENU = 0x12;
    private const ushort VK_A = 0x41;
    private const ushort VK_BACK = 0x08;

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT { public uint type; public InputUnion U; }
    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion {
        [FieldOffset(0)] public KEYBDINPUT ki;
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public HARDWAREINPUT hi;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT {
        public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public UIntPtr dwExtraInfo;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT {
        public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public UIntPtr dwExtraInfo;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct HARDWAREINPUT {
        public uint uMsg; public ushort wParamL; public ushort wParamH;
    }

    private static INPUT Key(ushort vk, uint flags) {
        return new INPUT { type = INPUT_KEYBOARD, U = new InputUnion { ki = new KEYBDINPUT { wVk = vk, wScan = 0, dwFlags = flags, time = 0, dwExtraInfo = UIntPtr.Zero } } };
    }

    private static INPUT Unicode(char ch, uint flags) {
        return new INPUT { type = INPUT_KEYBOARD, U = new InputUnion { ki = new KEYBDINPUT { wVk = 0, wScan = ch, dwFlags = KEYEVENTF_UNICODE | flags, time = 0, dwExtraInfo = UIntPtr.Zero } } };
    }

    private static INPUT ScanKey(ushort vk, bool keyUp, IntPtr layout) {
        uint scanEx = MapVirtualKeyEx(vk, MAPVK_VK_TO_VSC_EX, layout);
        ushort scan = (ushort)(scanEx & 0xFF);
        uint flags = KEYEVENTF_SCANCODE | (keyUp ? KEYEVENTF_KEYUP : 0);
        if ((scanEx & 0xE000) != 0) flags |= KEYEVENTF_EXTENDEDKEY;
        return new INPUT { type = INPUT_KEYBOARD, U = new InputUnion { ki = new KEYBDINPUT { wVk = 0, wScan = scan, dwFlags = flags, time = 0, dwExtraInfo = UIntPtr.Zero } } };
    }

    private static int AddMappedChar(List<INPUT> inputs, char ch, IntPtr layout) {
        short mapped = VkKeyScanEx(ch, layout);
        if (mapped == -1) {
            inputs.Add(Unicode(ch, 0));
            inputs.Add(Unicode(ch, KEYEVENTF_KEYUP));
            return 2;
        }

        ushort vk = (ushort)(mapped & 0x00FF);
        byte shiftState = (byte)((mapped >> 8) & 0xFF);
        var mods = new List<ushort>();
        if ((shiftState & 1) != 0) mods.Add(VK_SHIFT);
        if ((shiftState & 2) != 0) mods.Add(VK_CONTROL);
        if ((shiftState & 4) != 0) mods.Add(VK_MENU);

        foreach (ushort mod in mods) inputs.Add(ScanKey(mod, false, layout));
        inputs.Add(ScanKey(vk, false, layout));
        inputs.Add(ScanKey(vk, true, layout));
        for (int i = mods.Count - 1; i >= 0; i--) inputs.Add(ScanKey(mods[i], true, layout));
        return 2 + (2 * mods.Count);
    }

    private static uint SendBatch(List<INPUT> inputs) {
        if (inputs.Count == 0) return 0;
        return SendInput((uint)inputs.Count, inputs.ToArray(), Marshal.SizeOf(typeof(INPUT)));
    }

    public static uint SendText(string text, IntPtr hwnd) {
        uint total = 0;
        IntPtr layout = GetKeyboardLayout(GetWindowThreadProcessId(hwnd, IntPtr.Zero));

        // Limpa o valor atual sem usar ValuePattern. Cada etapa e enviada como
        // uma pequena sequencia e damos tempo para a fila de entrada do WPF
        // processar os eventos antes de continuar.
        var clear = new List<INPUT>();
        clear.Add(ScanKey(VK_CONTROL, false, layout));
        clear.Add(ScanKey(VK_A, false, layout));
        clear.Add(ScanKey(VK_A, true, layout));
        clear.Add(ScanKey(VK_CONTROL, true, layout));
        clear.Add(ScanKey(VK_BACK, false, layout));
        clear.Add(ScanKey(VK_BACK, true, layout));
        total += SendBatch(clear);
        System.Threading.Thread.Sleep(35);

        foreach (char ch in text) {
            var one = new List<INPUT>();
            AddMappedChar(one, ch, layout);
            uint accepted = SendBatch(one);
            total += accepted;
            System.Threading.Thread.Sleep(18);
        }
        return total;
    }

    public static int CountTextInputs(string text) {
        var probe = new List<INPUT>();
        IntPtr layout = GetKeyboardLayout(0);
        probe.Add(ScanKey(VK_CONTROL, false, layout));
        probe.Add(ScanKey(VK_A, false, layout));
        probe.Add(ScanKey(VK_A, true, layout));
        probe.Add(ScanKey(VK_CONTROL, true, layout));
        probe.Add(ScanKey(VK_BACK, false, layout));
        probe.Add(ScanKey(VK_BACK, true, layout));
        foreach (char ch in text) AddMappedChar(probe, ch, layout);
        return probe.Count;
    }
}
'@
                } catch {}
                $foregroundSeguro = $false
                $controleFocado = $false
                $fallbackExecutado = $false
                $physicalClickConfirmed = $false
                try {
                    $hwndInt = [Int64]$payload.hwnd
                    for ($tentativa = 0; $tentativa -lt 5 -and -not $foregroundSeguro; $tentativa++) {
                        [AurenUiWin32]::ShowWindow([IntPtr]$hwndInt, 9) | Out-Null
                        [AurenUiWin32]::SetForegroundWindow([IntPtr]$hwndInt) | Out-Null
                        Start-Sleep -Milliseconds (80 + ($tentativa * 60))
                        $foregroundAtual = [AurenUiWin32]::GetForegroundWindow()
                        $foregroundSeguro = ($foregroundAtual -eq [IntPtr]$hwndInt)
                    }
                } catch {}

                if ($foregroundSeguro) {
                    # PasswordBox nao expoe ValuePattern de forma segura. Antes de
                    # qualquer entrada de teclado, o controle protegido precisa receber foco
                    # tanto pela UI Automation quanto por uma interacao fisica real.
                    try {
                        $ponto = $item.Element.GetClickablePoint()
                        if ([AurenUiWin32]::SetCursorPos([int]$ponto.X, [int]$ponto.Y)) {
                            [AurenUiWin32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
                            Start-Sleep -Milliseconds 35
                            [AurenUiWin32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
                            $physicalClickConfirmed = $true
                        }
                    } catch {}

                    try { $item.Element.SetFocus() } catch {}
                    Start-Sleep -Milliseconds 140
                    try {
                        $focoAtual = [System.Windows.Automation.AutomationElement]::FocusedElement
                        if ($focoAtual) {
                            $focoNome = Safe-String $focoAtual.Current.Name
                            $focoId = Safe-String $focoAtual.Current.AutomationId
                            $controleFocado = (
                                ($focoId -and $item.AutomationId -and ($focoId -eq $item.AutomationId)) -or
                                ($focoNome -and $item.Name -and ($focoNome -eq $item.Name))
                            )
                        }
                    } catch {}

                    # A entrada fisica so pode ocorrer quando o HWND continua em
                    # primeiro plano, o clique fisico ocorreu e o controle exato
                    # foi confirmado como foco atual.
                    if ($controleFocado) {
                        try {
                            $foregroundAtual = [AurenUiWin32]::GetForegroundWindow()
                            $foregroundSeguro = ($foregroundAtual -eq [IntPtr]$hwndInt)
                        } catch {
                            $foregroundSeguro = $false
                        }
                    }

                    if ($foregroundSeguro -and $physicalClickConfirmed -and $controleFocado) {
                        try {
                            $inputCount = [AurenUiWin32]::SendText([string]$textoDesejado, [IntPtr]$hwndInt)
                            $esperado = [AurenUiWin32]::CountTextInputs([string]$textoDesejado)
                            $fallbackExecutado = ($inputCount -eq [uint32]$esperado)
                            Start-Sleep -Milliseconds 350
                        } catch {}
                    }
                }

                # Confirma novamente por um AutomationElement completamente novo.
                try {
                    $freshRoot = Get-RootElement ([string]$payload.hwnd)
                    $freshItems = Get-AllControls $freshRoot
                    $freshMatches = Find-Controls $freshItems $target 'Value'
                    if ($freshMatches.Count -gt 0) {
                        $freshItem = $freshMatches[0].Item
                        $freshPattern = $freshItem.Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                        $confirmado = Safe-String $freshPattern.Current.Value
                    }
                } catch {}
            }

            $confirmadoBool = ($confirmado -eq $textoDesejado)
            $confirmadoProtegidoSemLeitura = (
                [bool]$item.IsPassword -and
                $foregroundSeguro -and
                $physicalClickConfirmed -and
                $fallbackExecutado -and
                $controleFocado
            )
            if ($confirmadoProtegidoSemLeitura) {
                $confirmadoBool = $true
            }
            $resultado = [pscustomobject]@{
                ok=$true
                operacao='preencher'
                nome=$item.Name
                tipo=$item.ControlType
                automation_id=$item.AutomationId
                protegido=$item.IsPassword
                confirmado=$confirmadoBool
                entrada_fisica_executada=$fallbackExecutado
                controle_focado=$controleFocado
                clique_fisico_confirmado=$physicalClickConfirmed
                entrada_fisica_eventos_enviados=$(if ($item.IsPassword) { $inputCount } else { 0 })
                entrada_fisica_eventos_esperados=$(if ($item.IsPassword) { $esperado } else { 0 })
                entrada_fisica_ok=$fallbackExecutado
                resultado=$(if ($confirmadoProtegidoSemLeitura) {
                    "Preenchimento executado em controle protegido '$($item.Name)' ($($item.ControlType)); automation_id='$($item.AutomationId)'; protegido=True. O valor nao e legivel pela UI Automation."
                } elseif ($confirmadoBool) {
                    "Preenchimento concluido em '$($item.Name)' ($($item.ControlType)); automation_id='$($item.AutomationId)'; protegido=$($item.IsPassword)."
                } else {
                    "Preenchimento nao confirmado em '$($item.Name)' ($($item.ControlType)); automation_id='$($item.AutomationId)'; protegido=$($item.IsPassword); fallback_foreground_confirmado=$foregroundSeguro; controle_focado=$controleFocado."
                })
            }
        } elseif ($payload.operacao -eq 'alternar') {
            if (-not ($item.Patterns -contains 'Toggle')) { throw "O controle '$($item.Name)' nao oferece TogglePattern." }
            $pattern = $item.Element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
            $pattern.Toggle()
            Start-Sleep -Milliseconds 120
            $estado = Safe-String $pattern.Current.ToggleState
            $resultado = [pscustomobject]@{ ok=$true; operacao='alternar'; nome=$item.Name; tipo=$item.ControlType; estado=$estado; resultado="Estado alternado de '$($item.Name)': $estado." }
        } elseif ($payload.operacao -eq 'selecionar') {
            if (-not ($item.Patterns -contains 'SelectionItem')) { throw "O controle '$($item.Name)' nao oferece SelectionItemPattern." }
            $pattern = $item.Element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
            $pattern.Select()
            Start-Sleep -Milliseconds 120
            $selecionado = [bool]$pattern.Current.IsSelected
            $resultado = [pscustomobject]@{ ok=$true; operacao='selecionar'; nome=$item.Name; tipo=$item.ControlType; selecionado=$selecionado; resultado="Elemento selecionado: '$($item.Name)'." }
        } else {
            throw "Operacao UI Automation desconhecida: $($payload.operacao)"
        }
    }
    return $resultado
    } catch {
        return [pscustomobject]@{
            ok=$false
            erro=(Safe-String $_.Exception.Message)
            tipo=(Safe-String $_.Exception.GetType().FullName)
        }
    }
}

while ($true) {
    $linha = [Console]::ReadLine()
    if ($null -eq $linha) { break }
    if ([string]::IsNullOrWhiteSpace($linha)) { continue }

    try {
        $payload = $linha | ConvertFrom-Json
        $resultado = Invoke-AurenOperation $payload
    } catch {
        $resultado = [pscustomobject]@{
            ok=$false
            erro=(Safe-String $_.Exception.Message)
            tipo=(Safe-String $_.Exception.GetType().FullName)
        }
    }

    $json = $resultado | ConvertTo-Json -Compress -Depth 7
    Write-Output ([string]$json)
    [Console]::Out.Flush()
}

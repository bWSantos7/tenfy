$ErrorActionPreference = "Continue"

function Step($m) {
  Write-Host ""
  Write-Host "============================================================"
  Write-Host " $m"
  Write-Host "============================================================"
}

function Info($m) { Write-Host "[INFO] $m" }
function Warn($m) { Write-Host "[WARN] $m" }

function Ensure-Dirs {
  @(
    ".tools\ai-agents\logs",
    ".tools\ai-agents\prompts",
    ".tools\ai-agents\queue",
    ".tools\ai-agents\queue\done",
    ".tools\ai-agents\reports",
    ".tools\ai-agents\state"
  ) | ForEach-Object {
    New-Item -ItemType Directory -Force $_ | Out-Null
  }
}

function Is-Main-Branch {
  $b = git branch --show-current
  return ($b -eq "main" -or $b -eq "master")
}

function Next-Task {
  return Get-ChildItem ".tools\ai-agents\queue" -Filter "*.md" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notlike "*\done\*" } |
    Sort-Object Name |
    Select-Object -First 1
}

function Has-Limit-Error($log) {
  if (!(Test-Path $log)) { return $false }
  $c = Get-Content $log -Raw -ErrorAction SilentlyContinue
  return ($c -match "rate limit|quota|usage limit|limit reached|too many requests|429|tokens|exceeded|try again later|daily limit|weekly limit|monthly limit|credit balance|overloaded|capacity")
}

function Run-With-Retry($name, $expected, $log, $minutes, [scriptblock]$cmd) {
  for ($i = 1; $i -le 999; $i++) {
    Step "$name - tentativa $i"

    try {
      & $cmd
    } catch {
      $_ | Out-String | Add-Content $log -Encoding UTF8
    }

    if (Test-Path $expected) {
      Info "$name concluiu: $expected"
      return $true
    }

    if (Has-Limit-Error $log) {
      Warn "$name bateu limite/token/quota. Aguardando $minutes minutos."
    } else {
      Warn "$name não gerou o arquivo esperado. Aguardando $minutes minutos."
    }

    Start-Sleep -Seconds ($minutes * 60)
  }

  return $false
}

Ensure-Dirs

if (Is-Main-Branch) {
  Write-Host "[ERRO] Você está na main/master. Crie uma branch antes."
  Write-Host "git checkout -b ai/autonomous-mvp"
  exit 1
}

if (!(Test-Path ".tools\ai-agents\state\status.json")) {
@'
{
  "status": "running",
  "cycle": 0,
  "max_cycles": 50,
  "current_task": null,
  "last_agent": null,
  "final_verdict": null,
  "stop_reason": null,
  "last_error": null
}
'@ | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8
}

if (!(Get-ChildItem ".tools\ai-agents\queue" -Filter "*.md" -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notlike "*\done\*" })) {
  if (Test-Path ".tools\ai-agents\start.md") {
    Copy-Item ".tools\ai-agents\start.md" ".tools\ai-agents\queue\000-start.md" -Force
  }
}

$status = Get-Content ".tools\ai-agents\state\status.json" -Raw | ConvertFrom-Json
$max = [int]$status.max_cycles
if ($max -le 0) { $max = 50 }

$startCycle = [int]$status.cycle + 1
if ($startCycle -lt 1) { $startCycle = 1 }

for ($cycle = $startCycle; $cycle -le $max; $cycle++) {
  $task = Next-Task
  if ($null -eq $task) {
    Info "Nenhuma task pendente."
    break
  }

  $taskContent = Get-Content $task.FullName -Raw
  $log = ".tools\ai-agents\logs\cycle-$cycle.log"
  "CICLO $cycle - Task $($task.Name)" | Set-Content $log -Encoding UTF8

  Step "CICLO $cycle - $($task.Name)"

  $status.status = "running"
  $status.cycle = $cycle
  $status.current_task = $task.Name
  $status.last_agent = "claude"
  $status.last_error = $null
  $status | ConvertTo-Json -Depth 10 | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8

  # ============================================================
  # CLAUDE EXECUTOR
  # ============================================================

  $claudeTemplate = (Get-Content ".tools\ai-agents\prompts\01-claude-executor.md" -Raw).Replace("CYCLE_ID", "$cycle")
  $claudePrompt = @"
$claudeTemplate

# TASK ATUAL
$taskContent

# CONTEXTO IMPORTANTE
Você está trabalhando no Tennis Hub.
Antes de qualquer alteração, leia CLAUDE.md e AI_CONTEXT.md.
Se a task citar escopo_contrato, leia também escopo_contrato.pdf quando necessário.

Ao terminar, crie obrigatoriamente:
.tools/ai-agents/reports/claude-cycle-$cycle.md
"@

  $claudePrompt | Set-Content ".tools\ai-agents\logs\claude-prompt-cycle-$cycle.md" -Encoding UTF8

  $claudeReport = ".tools\ai-agents\reports\claude-cycle-$cycle.md"

  $ok = Run-With-Retry "CLAUDE EXECUTOR" $claudeReport $log 60 {
    claude -p "$claudePrompt" --allowedTools "Read,Write,Edit,MultiEdit,Bash" --dangerously-skip-permissions *>> $log
  }

  if (!$ok) {
    $status.status = "paused"
    $status.last_agent = "claude"
    $status.last_error = "Claude nao gerou relatorio."
    $status | ConvertTo-Json -Depth 10 | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8
    exit 1
  }

  # ============================================================
  # CODEX AUDITOR
  # ============================================================

  $status.last_agent = "codex-auditor"
  $status | ConvertTo-Json -Depth 10 | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8

  $codexTemplate = (Get-Content ".tools\ai-agents\prompts\02-gpt-auditor.md" -Raw).Replace("CYCLE_ID", "$cycle")
  $claudeText = Get-Content $claudeReport -Raw
  $diff = git diff

  $codexPrompt = @"
$codexTemplate

# TASK ATUAL
$taskContent

# RELATORIO DO CLAUDE
$claudeText

# DIFF ATUAL
$diff

# INSTRUÇÃO CRÍTICA
Você deve auditar a implementação, corrigir problemas pequenos se for seguro e criar obrigatoriamente:
.tools/ai-agents/reports/gpt-cycle-$cycle.md

Não responda apenas no terminal.
"@

  $codexPromptFile = ".tools\ai-agents\logs\gpt-prompt-cycle-$cycle.md"
  $codexPrompt | Set-Content $codexPromptFile -Encoding UTF8

  $codexReport = ".tools\ai-agents\reports\gpt-cycle-$cycle.md"

  $codexCommandPrompt = "Leia integralmente o arquivo .tools/ai-agents/logs/gpt-prompt-cycle-$cycle.md e execute a auditoria solicitada. Você deve obrigatoriamente criar o arquivo .tools/ai-agents/reports/gpt-cycle-$cycle.md. Não responda apenas no terminal."

  $ok = Run-With-Retry "CODEX AUDITOR" $codexReport $log 30 {
    $out = & codex exec --sandbox danger-full-access "$codexCommandPrompt" 2>&1
    $out | Add-Content $log -Encoding UTF8

    if (!(Test-Path $codexReport)) {
      $out | Set-Content $codexReport -Encoding UTF8
    }
  }

  if (!$ok) {
    $status.status = "paused"
    $status.last_agent = "codex-auditor"
    $status.last_error = "Codex nao gerou relatorio."
    $status | ConvertTo-Json -Depth 10 | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8
    exit 1
  }

  # ============================================================
  # CHECKS AUTOMATICOS
  # ============================================================

  Step "CHECKS AUTOMATICOS"

  if (Test-Path "frontend\package.json") {
    Push-Location "frontend"
    npm run lint --if-present *>> "..\$log"
    npm run test --if-present *>> "..\$log"
    npm run build --if-present *>> "..\$log"
    Pop-Location
  }

  if (Test-Path "mobile\package.json") {
    Push-Location "mobile"
    npm run lint --if-present *>> "..\$log"
    npm run test --if-present *>> "..\$log"
    npm run build --if-present *>> "..\$log"
    Pop-Location
  }

  if (Test-Path "backend\manage.py") {
    Push-Location "backend"
    python manage.py check *>> "..\$log"
    Pop-Location
  }

  # ============================================================
  # CODEX PLANNER
  # ============================================================

  $status.last_agent = "codex-planner"
  $status | ConvertTo-Json -Depth 10 | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8

  $plannerTemplate = Get-Content ".tools\ai-agents\prompts\04-task-planner.md" -Raw
  $codexText = Get-Content $codexReport -Raw
  $nextCycle = $cycle + 1
  $nextTaskFile = "{0:D3}-auto-cycle-{1}.md" -f $nextCycle, $nextCycle
  $nextTask = ".tools\ai-agents\queue\$nextTaskFile"
  $finalReport = ".tools\ai-agents\reports\FINAL-REPORT.md"
  $diff2 = git diff

  $plannerPrompt = @"
$plannerTemplate

# CICLO ATUAL
$cycle

# PROXIMO CICLO
$nextCycle

# NEXT_TASK_FILE
$nextTaskFile

# TASK ATUAL
$taskContent

# RELATORIO CLAUDE
$claudeText

# RELATORIO CODEX
$codexText

# DIFF ATUAL
$diff2

# INSTRUÇÃO CRÍTICA
Se ainda houver trabalho, crie exatamente:
.tools/ai-agents/queue/$nextTaskFile

Se estiver pronto, crie:
.tools/ai-agents/reports/FINAL-REPORT.md

Não responda apenas no terminal.
"@

  $plannerPromptFile = ".tools\ai-agents\logs\planner-prompt-cycle-$cycle.md"
  $plannerPrompt | Set-Content $plannerPromptFile -Encoding UTF8

  $plannerCommandPrompt = "Leia integralmente o arquivo .tools/ai-agents/logs/planner-prompt-cycle-$cycle.md e execute o planejamento solicitado. Se ainda houver trabalho, crie .tools/ai-agents/queue/$nextTaskFile. Se o projeto estiver pronto, crie .tools/ai-agents/reports/FINAL-REPORT.md. Não responda apenas no terminal."

  $ok = $false

  for ($p = 1; $p -le 999; $p++) {
    Step "CODEX PLANNER - tentativa $p"

    $out = & codex exec --sandbox danger-full-access "$plannerCommandPrompt" 2>&1
    $out | Add-Content $log -Encoding UTF8

    if ((Test-Path $nextTask) -or (Test-Path $finalReport)) {
      $ok = $true
      break
    }

    Warn "Planner não criou próxima task nem FINAL-REPORT. Aguardando 30 minutos."
    Start-Sleep -Seconds (30 * 60)
  }

  if (!$ok) {
    $status.status = "paused"
    $status.last_agent = "codex-planner"
    $status.last_error = "Planner nao criou proxima task ou final report."
    $status | ConvertTo-Json -Depth 10 | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8
    exit 1
  }

  Move-Item $task.FullName ".tools\ai-agents\queue\done\$($task.Name)" -Force

  Step "COMMIT AUTOMATICO"
  git add . *>> $log

  if (!( [string]::IsNullOrWhiteSpace((git status --porcelain)) )) {
    git commit -m "ai: autonomous cycle $cycle - $($task.BaseName)" *>> $log
  }

  if (Test-Path $finalReport) {
    $status.status = "finished"
    $status.final_verdict = "check_FINAL_REPORT"
    $status.stop_reason = "FINAL-REPORT.md generated"
    $status.last_agent = "codex-planner"
    $status | ConvertTo-Json -Depth 10 | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8
    Step "FINALIZADO"
    break
  }

  Start-Sleep -Seconds 10
}

Step "PROCESSO ENCERRADO"
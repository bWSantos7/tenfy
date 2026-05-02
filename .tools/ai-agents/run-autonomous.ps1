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
  ) | ForEach-Object { New-Item -ItemType Directory -Force $_ | Out-Null }
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
  return ($c -match "rate limit|quota|usage limit|limit reached|too many requests|429|tokens|exceeded|try again later|daily limit|weekly limit|monthly limit")
}

function Run-With-Retry($name, $expected, $log, $minutes, [scriptblock]$cmd) {
  for ($i = 1; $i -le 999; $i++) {
    Step "$name - tentativa $i"
    try { & $cmd } catch { $_ | Out-String | Add-Content $log -Encoding UTF8 }
    if (Test-Path $expected) { Info "$name concluiu: $expected"; return $true }
    if (Has-Limit-Error $log) { Warn "$name bateu limite/token/quota. Aguardando $minutes minutos." }
    else { Warn "$name nao gerou o relatorio esperado. Aguardando $minutes minutos." }
    Start-Sleep -Seconds ($minutes * 60)
  }
  return $false
}

Ensure-Dirs

if (Is-Main-Branch) {
  Write-Host "[ERRO] Voce esta na main/master. Crie uma branch antes."
  Write-Host "git checkout -b ai/autonomous-mvp"
  exit 1
}

if (!(Test-Path ".tools\ai-agents\state\status.json")) {
  @{
    status = "running"; cycle = 0; max_cycles = 20; current_task = $null; last_agent = $null; final_verdict = $null; stop_reason = $null; last_error = $null
  } | ConvertTo-Json -Depth 10 | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8
}

if (!(Get-ChildItem ".tools\ai-agents\queue" -Filter "*.md" -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notlike "*\done\*" })) {
  if (Test-Path ".tools\ai-agents\start.md") { Copy-Item ".tools\ai-agents\start.md" ".tools\ai-agents\queue\000-start.md" -Force }
}

$status = Get-Content ".tools\ai-agents\state\status.json" -Raw | ConvertFrom-Json
$max = [int]$status.max_cycles
if ($max -le 0) { $max = 20 }

$startCycle = [int]$status.cycle + 1
if ($startCycle -lt 1) { $startCycle = 1 }

for ($cycle = $startCycle; $cycle -le $max; $cycle++) {
  $task = Next-Task
  if ($null -eq $task) { Info "Nenhuma task pendente."; break }

  $taskContent = Get-Content $task.FullName -Raw
  $log = ".tools\ai-agents\logs\cycle-$cycle.log"
  "CICLO $cycle - Task $($task.Name)" | Set-Content $log -Encoding UTF8
  Step "CICLO $cycle - $($task.Name)"

  $status.status = "running"
  $status.cycle = $cycle
  $status.current_task = $task.Name
  $status.last_error = $null
  $status | ConvertTo-Json -Depth 10 | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8

  $claudeTemplate = (Get-Content ".tools\ai-agents\prompts\01-claude-executor.md" -Raw).Replace("CYCLE_ID", "$cycle")
  $claudePrompt = @"
$claudeTemplate

# TASK ATUAL
$taskContent

Ao terminar, crie:
.tools/ai-agents/reports/claude-cycle-$cycle.md
"@
  $claudePrompt | Set-Content ".tools\ai-agents\logs\claude-prompt-cycle-$cycle.md" -Encoding UTF8

  $claudeReport = ".tools\ai-agents\reports\claude-cycle-$cycle.md"
  $ok = Run-With-Retry "CLAUDE EXECUTOR" $claudeReport $log 60 {
    claude -p "$claudePrompt" --allowedTools "Read,Write,Edit,MultiEdit,Bash" --dangerously-skip-permissions *>> $log
  }
  if (!$ok) { exit 1 }

  $gptTemplate = (Get-Content ".tools\ai-agents\prompts\02-gpt-auditor.md" -Raw).Replace("CYCLE_ID", "$cycle")
  $claudeText = Get-Content $claudeReport -Raw
  $diff = git diff
  $gptPrompt = @"
$gptTemplate

# TASK ATUAL
$taskContent

# RELATORIO DO CLAUDE
$claudeText

# DIFF
$diff

Ao terminar, crie:
.tools/ai-agents/reports/gpt-cycle-$cycle.md
"@
  $gptPrompt | Set-Content ".tools\ai-agents\logs\gpt-prompt-cycle-$cycle.md" -Encoding UTF8

  $gptReport = ".tools\ai-agents\reports\gpt-cycle-$cycle.md"
  $ok = Run-With-Retry "GPT/CODEX AUDITOR" $gptReport $log 30 {
    codex exec --sandbox danger-full-access "$gptPrompt" *>> $log
  }
  if (!$ok) { exit 1 }

  $geminiTemplate = (Get-Content ".tools\ai-agents\prompts\03-gemini-qa.md" -Raw).Replace("CYCLE_ID", "$cycle")
  $gptText = Get-Content $gptReport -Raw
  $diff2 = git diff
  $geminiPrompt = @"
$geminiTemplate

# TASK ATUAL
$taskContent

# RELATORIO DO CLAUDE
$claudeText

# RELATORIO DO GPT
$gptText

# DIFF
$diff2

Ao terminar, crie:
.tools/ai-agents/reports/gemini-cycle-$cycle.md
"@
  $geminiPrompt | Set-Content ".tools\ai-agents\logs\gemini-prompt-cycle-$cycle.md" -Encoding UTF8

  $geminiReport = ".tools\ai-agents\reports\gemini-cycle-$cycle.md"
  $ok = Run-With-Retry "GEMINI QA" $geminiReport $log 30 {
    gemini -p "$geminiPrompt" --output-format text --skip-trust *>> $log
  }
  if (!$ok) { exit 1 }

  Step "CHECKS AUTOMATICOS"
  if (Test-Path "frontend\package.json") { Push-Location "frontend"; npm run lint --if-present *>> "..\$log"; npm run test --if-present *>> "..\$log"; npm run build --if-present *>> "..\$log"; Pop-Location }
  if (Test-Path "mobile\package.json") { Push-Location "mobile"; npm run lint --if-present *>> "..\$log"; npm run test --if-present *>> "..\$log"; npm run build --if-present *>> "..\$log"; Pop-Location }
  if (Test-Path "backend\manage.py") { Push-Location "backend"; python manage.py check *>> "..\$log"; Pop-Location }

  $plannerTemplate = Get-Content ".tools\ai-agents\prompts\04-task-planner.md" -Raw
  $geminiText = Get-Content $geminiReport -Raw
  $nextCycle = $cycle + 1
  $nextTaskFile = "{0:D3}-auto-cycle-{1}.md" -f $nextCycle, $nextCycle
  $nextTask = ".tools\ai-agents\queue\$nextTaskFile"
  $finalReport = ".tools\ai-agents\reports\FINAL-REPORT.md"
  $diff3 = git diff
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

# RELATORIO GPT
$gptText

# RELATORIO GEMINI
$geminiText

# DIFF
$diff3

Se ainda houver trabalho, crie exatamente:
.tools/ai-agents/queue/$nextTaskFile

Se estiver pronto, crie:
.tools/ai-agents/reports/FINAL-REPORT.md
"@
  $plannerPrompt | Set-Content ".tools\ai-agents\logs\planner-prompt-cycle-$cycle.md" -Encoding UTF8

  $ok = $false
  for ($p = 1; $p -le 999; $p++) {
    Step "TASK PLANNER - tentativa $p"
    codex exec --sandbox danger-full-access "$plannerPrompt" *>> $log
    if ((Test-Path $nextTask) -or (Test-Path $finalReport)) { $ok = $true; break }
    Warn "Planner nao criou proxima task nem FINAL-REPORT. Aguardando 30 minutos."
    Start-Sleep -Seconds (30 * 60)
  }
  if (!$ok) { exit 1 }

  Move-Item $task.FullName ".tools\ai-agents\queue\done\$($task.Name)" -Force

  Step "COMMIT AUTOMATICO"
  git add . *>> $log
  if (!([string]::IsNullOrWhiteSpace((git status --porcelain)))) { git commit -m "ai: autonomous cycle $cycle - $($task.BaseName)" *>> $log }

  if (Test-Path $finalReport) {
    $status.status = "finished"
    $status.final_verdict = "check_FINAL_REPORT"
    $status.stop_reason = "FINAL-REPORT.md generated"
    $status | ConvertTo-Json -Depth 10 | Set-Content ".tools\ai-agents\state\status.json" -Encoding UTF8
    Step "FINALIZADO"
    break
  }

  Start-Sleep -Seconds 10
}

Step "PROCESSO ENCERRADO"

#requires -Version 5.1
<#
.SYNOPSIS
  Установка скилла warehouse-storekeeper для Hermes Agent (Windows).

.DESCRIPTION
  1. Проверяет наличие Python 3.10+.
  2. Создаёт .venv в папке скилла и устанавливает зависимости.
  3. Копирует скилл в %LOCALAPPDATA%\hermes\skills\warehouse-storekeeper.
  4. Создаёт %LOCALAPPDATA%\WarehouseAgent\secrets\ и кладёт шаблон syncserver.env.
  5. Выставляет ACL на файл секретов (protect_secrets.ps1).
  6. Печатает итоговое дерево и подсказку по проверке hermes skills list.

.PARAMETER SkipHermesInstall
  Только окружение (.venv, секреты), без копирования в каталог скиллов Hermes.

.EXAMPLE
  .\scripts\bootstrap.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipHermesInstall
)

$ErrorActionPreference = "Stop"
$SkillSourceDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$HermesSkillsRoot = Join-Path $env:LOCALAPPDATA "hermes\skills"
$HermesSkillDir   = Join-Path $HermesSkillsRoot "warehouse-storekeeper"
$SecretsDir       = Join-Path $env:LOCALAPPDATA "WarehouseAgent\secrets"
$SecretsFile      = Join-Path $SecretsDir "syncserver.env"

Write-Host "== warehouse-storekeeper bootstrap ==" -ForegroundColor Cyan
Write-Host "Источник: $SkillSourceDir"

# --- 1. Python -------------------------------------------------------------
$Python = $null
foreach ($candidate in @("python", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $ver -match "Python 3\.(\d+)") {
            if ([int]$Matches[1] -ge 10) { $Python = $candidate; break }
        }
    } catch { }
}
if (-not $Python) {
    Write-Error "Python 3.10+ не найден в PATH. Установите Python с python.org и повторите."
    exit 1
}
Write-Host "[OK] $(& $Python --version)"

# --- 2. venv + зависимости --------------------------------------------------
$VenvDir = Join-Path $SkillSourceDir ".venv"
if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
    Write-Host "Создаю venv: $VenvDir"
    & $Python -m venv $VenvDir
}
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r (Join-Path $SkillSourceDir "requirements.txt")
Write-Host "[OK] Зависимости установлены в .venv"

# --- 3. Копирование в каталог скиллов Hermes --------------------------------
if (-not $SkipHermesInstall) {
    if ($SkillSourceDir -ne $HermesSkillDir) {
        New-Item -ItemType Directory -Force -Path $HermesSkillsRoot | Out-Null
        if (Test-Path $HermesSkillDir) {
            Write-Host "Обновляю $HermesSkillDir"
        }
        New-Item -ItemType Directory -Force -Path $HermesSkillDir | Out-Null
        $exclude = @(".venv", "__pycache__", ".pytest_cache")
        Get-ChildItem $SkillSourceDir -Recurse | Where-Object {
            $rel = $_.FullName.Substring($SkillSourceDir.Length)
            -not ($exclude | Where-Object { $rel -like "*\$_\*" -or $rel -like "*\$_" })
        } | ForEach-Object {
            $target = Join-Path $HermesSkillDir $_.FullName.Substring($SkillSourceDir.Length)
            if ($_.PSIsContainer) { New-Item -ItemType Directory -Force -Path $target | Out-Null }
            else { Copy-Item $_.FullName $target -Force }
        }
        Write-Host "[OK] Скилл установлен: $HermesSkillDir"
    } else {
        Write-Host "[OK] Скилл уже на месте: $HermesSkillDir"
    }
}

# --- 4. Файл секретов --------------------------------------------------------
New-Item -ItemType Directory -Force -Path $SecretsDir | Out-Null
if (-not (Test-Path $SecretsFile)) {
    Copy-Item (Join-Path $SkillSourceDir "templates\syncserver.env.example") $SecretsFile
    Write-Host "[OK] Создан шаблон: $SecretsFile"
    Write-Host "     >>> Заполните SYNC_SERVER_BASE_URL и SYNC_SERVER_USER_TOKEN <<<" -ForegroundColor Yellow
} else {
    Write-Host "[OK] Файл секретов уже существует (не перезаписываю)"
}

# --- 5. ACL ------------------------------------------------------------------
& (Join-Path $SkillSourceDir "scripts\protect_secrets.ps1") -Path $SecretsFile

# --- 6. Итог ------------------------------------------------------------------
Write-Host ""
Write-Host "== Готово. Проверка регистрации скилла: ==" -ForegroundColor Cyan
Write-Host '& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe" skills list'
Write-Host '  ожидается: warehouse-storekeeper | local | local | enabled'
Write-Host ""
Write-Host "== Дерево установленного скилла: =="
if (Test-Path $HermesSkillDir) {
    Get-ChildItem $HermesSkillDir -Recurse | ForEach-Object { $_.FullName }
}
Write-Host ""
Write-Host "Следующий шаг: заполните токены в $SecretsFile и выполните scripts\smoke_test.ps1"

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$NpmCache = Join-Path $ProjectRoot ".npm-cache"

function Require-Command {
  param(
    [string]$Name,
    [string]$Hint
  )
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "$Name not found. $Hint"
  }
}

function Get-NpmCommand {
  $npmCmd = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
  if ($npmCmd) { return $npmCmd.Source }
  $npm = Get-Command "npm" -ErrorAction SilentlyContinue
  if ($npm) { return $npm.Source }
  throw "npm not found. Please install Node.js 20 or newer."
}

Write-Host "== 被动收益 Agent Windows 本地安装 ==" -ForegroundColor Green
Write-Host "Project: $ProjectRoot"

Require-Command "python" "Please install Python 3.11 or newer and add it to PATH."
Require-Command "node" "Please install Node.js 20 or newer and add it to PATH."
$Npm = Get-NpmCommand

Write-Host "Python: $(& python --version)"
Write-Host "Node: $(& node --version)"
Write-Host "NPM: $(& $Npm --version)"

if (-not (Test-Path $VenvPython)) {
  Write-Host "Creating backend virtual environment..."
  Push-Location $BackendDir
  & python -m venv .venv
  Pop-Location
}

Write-Host "Installing backend dependencies..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $BackendDir "requirements.txt")

Write-Host "Installing frontend dependencies..."
Push-Location $FrontendDir
if (Test-Path (Join-Path $FrontendDir "package-lock.json")) {
  & $Npm --cache $NpmCache ci
} else {
  & $Npm --cache $NpmCache install
}
Pop-Location

$EnvFile = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"
if ((-not (Test-Path $EnvFile)) -and (Test-Path $EnvExample)) {
  Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
  Write-Host "Created .env from .env.example. You can fill API settings later in the app Settings page."
}

Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
Write-Host "Start with: powershell -ExecutionPolicy Bypass -File .\scripts\start_windows.ps1"

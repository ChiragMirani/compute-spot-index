$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\chira\anaconda3\python.exe"
$port = 8788

$listener = netstat -ano | Select-String ":$port\s" | Select-Object -First 1
if ($listener) {
  Write-Host "Port $port already appears to be in use. Close the existing tracker server if live refresh still does not work."
}

if (-not $env:VAST_API_KEY) {
  $secure = Read-Host "Paste new Vast.ai API key" -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $env:VAST_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  }
  finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
  }
}

Write-Host ""
Write-Host "Starting GPU Spot Price Index..."
Write-Host "Open: http://127.0.0.1:$port"
Write-Host "Click Refresh Vast Prices to fetch live offers."
Write-Host ""

Set-Location $root
& $python server.py

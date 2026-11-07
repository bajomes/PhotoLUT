#Requires -Version 5.1
$ErrorActionPreference = "Stop"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is required. Install Docker Desktop first." }
docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Compose v2 plugin is required." }
docker info | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop/Engine is not running or inaccessible." }
Write-Host "Building and starting PhotoLUT..."
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw "docker compose failed. Inspect 'docker compose logs'." }
$url = if ($env:PHOTOLUT_URL) { $env:PHOTOLUT_URL } else { "http://127.0.0.1:8000" }
for ($attempt = 0; $attempt -lt 45; $attempt++) {
  try { Invoke-WebRequest -Uri "$url/" -TimeoutSec 3 -UseBasicParsing | Out-Null; Write-Host "PhotoLUT is ready: $url"; exit 0 }
  catch { Start-Sleep -Seconds 2 }
}
docker compose logs --tail 100
throw "PhotoLUT did not become ready at $url."

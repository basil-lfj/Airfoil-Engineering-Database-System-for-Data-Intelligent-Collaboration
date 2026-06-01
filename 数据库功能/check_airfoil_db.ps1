param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$Query = "select current_database(), current_user;"
)

function Read-LooseEnv([string]$Path) {
  $cfg = @{
    host = $null
    port = $null
    password = $null
  }

  if (-not (Test-Path -LiteralPath $Path)) {
    throw "env file not found: $Path"
  }

  foreach ($raw in Get-Content -LiteralPath $Path -Encoding UTF8) {
    $line = $raw.Trim()
    if ($line.Length -eq 0) { continue }
    if ($line.StartsWith("#")) { continue }

    if ($line.Contains("=")) {
      $parts = $line.Split("=", 2)
      $k = $parts[0].Trim()
      $v = $parts[1].Trim()
      if ($k -eq "host") { $cfg.host = $v; continue }
      if ($k -eq "port") { $cfg.port = [int]$v; continue }
      if ($k -eq "password") { $cfg.password = $v; continue }
      continue
    }

    if (-not $cfg.host) { $cfg.host = $line }
  }

  return $cfg
}

function Read-PgService([string]$Path) {
  $cfg = @{
    host = $null
    port = $null
    dbname = $null
    user = $null
  }

  if (-not (Test-Path -LiteralPath $Path)) {
    return $cfg
  }

  $inSection = $false
  foreach ($raw in Get-Content -LiteralPath $Path -Encoding UTF8) {
    $line = $raw.Trim()
    if ($line.Length -eq 0) { continue }
    if ($line.StartsWith("#")) { continue }

    if ($line.StartsWith("[") -and $line.EndsWith("]")) {
      if (-not $inSection) { $inSection = $true; continue }
      break
    }

    if (-not $inSection) { continue }
    if (-not $line.Contains("=")) { continue }

    $parts = $line.Split("=", 2)
    $k = $parts[0].Trim()
    $v = $parts[1].Trim()

    if ($k -eq "host") { $cfg.host = $v; continue }
    if ($k -eq "port") { $cfg.port = [int]$v; continue }
    if ($k -eq "dbname") { $cfg.dbname = $v; continue }
    if ($k -eq "user") { $cfg.user = $v; continue }
  }

  return $cfg
}

$envFile = Join-Path $Root ".env"
$serviceFile = Join-Path $Root "数据库设计\\sql\\pg_service.conf"

$envCfg = Read-LooseEnv $envFile
$svcCfg = Read-PgService $serviceFile

$dbHost = if ($envCfg.host) { $envCfg.host } elseif ($svcCfg.host) { $svcCfg.host } else { "localhost" }
$dbPort = if ($envCfg.port) { $envCfg.port } elseif ($svcCfg.port) { $svcCfg.port } else { 5432 }
$dbName = if ($svcCfg.dbname) { $svcCfg.dbname } else { "postgres" }
$dbUser = if ($svcCfg.user) { $svcCfg.user } else { "postgres" }
$password = $envCfg.password

if (-not $password) {
  throw "password not found in .env"
}

$env:PGPASSWORD = $password
try {
  & psql -h $dbHost -p $dbPort -U $dbUser -d $dbName -v ON_ERROR_STOP=1 -c $Query | Out-Host
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
  Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}


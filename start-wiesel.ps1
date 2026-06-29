# start-wiesel.ps1
# Startet alle Wiesel-Services beim Login

$LogFile = "C:\Users\tillt\wiesel\start-wiesel.log"
$ProjectDir = "C:\Users\tillt\wiesel"

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

function IsRunning($processName) {
    return (Get-Process -Name $processName -ErrorAction SilentlyContinue) -ne $null
}

Log "=== Wiesel Autostart ==="

# 1. Docker Desktop starten
Log "[1/7] Docker Desktop starten..."
if (-not (IsRunning "Docker Desktop")) {
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
} else {
    Log "      Docker Desktop läuft bereits"
}

Log "      Warte auf Docker..."
$timeout = 120
$elapsed = 0
$ready = $false
while ($elapsed -lt $timeout) {
    $result = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Log "      Docker ist ready!"
        $ready = $true
        break
    }
    Start-Sleep -Seconds 3
    $elapsed += 3
    Log "      ...warte ($elapsed s)"
}

if (-not $ready) {
    Log "      [WARN] Docker Timeout - fahre trotzdem fort"
}

# 2. Docker Compose starten
Log "[2/7] Docker Compose starten..."
Set-Location $ProjectDir
Start-Process "docker" -ArgumentList "compose up -d" -WindowStyle Hidden -Wait
Start-Sleep -Seconds 5

# 3. VS Code öffnen
Log "[3/7] VS Code starten..."
if (-not (IsRunning "Code")) {
    Start-Process "code" -ArgumentList $ProjectDir
    Log "      VS Code geöffnet mit $ProjectDir"
} else {
    Log "      VS Code läuft bereits"
}

# 4. Cloudflare Tunnel wiesel-bot
Log "[4/7] Cloudflare Tunnel wiesel-bot starten..."
Start-Process "cloudflared" -ArgumentList "tunnel run --url http://localhost:8001 wiesel-bot" -WindowStyle Minimized

# 5. Cloudflare Tunnel unwritten-bot
Log "[5/7] Cloudflare Tunnel unwritten-bot starten..."
Start-Process "cloudflared" -ArgumentList "tunnel run --url http://localhost:3000 unwritten-bot" -WindowStyle Minimized

# 6. Cloudflare Tunnel wiesel-docs
Log "[6/7] Cloudflare Tunnel wiesel-docs starten..."
Start-Process "cloudflared" -ArgumentList "tunnel run --url http://localhost:8080 wiesel-docs" -WindowStyle Minimized

# 7. Hermes Gateway im VS Code Terminal
Log "[7/7] Hermes Gateway in VS Code Terminal starten..."
Start-Sleep -Seconds 4
Start-Process "code" -ArgumentList ("--reuse-window", $ProjectDir)
Start-Sleep -Seconds 5
Start-Process "powershell" -ArgumentList "-ExecutionPolicy Bypass -NoExit -Command hermes gateway run --replace" -WindowStyle Normal

Log "Alle Services gestartet!"
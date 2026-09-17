<#
Puts one of Sukoon's backups back in place of the shop's database (ADR-0037 §7). Run as Administrator:

  powershell -ExecutionPolicy Bypass -File "C:\Program Files\Sukoon\setup\restore-backup.ps1" `
      -Backup "C:\ProgramData\Sukoon\backups\sukoon-20260919-101500.db"

Everything since that backup is lost — sales, stock, Khata payments — so choose the newest backup
from before the problem. The current database is NOT deleted: it is kept first, so a restore can
itself be undone.
#>
param(
    [Parameter(Mandatory = $true)] [string] $Backup,
    [int] $Port = 5000
)

$ErrorActionPreference = "Stop"
$TaskName = "Sukoon Server"
$DataDir  = Join-Path $env:ProgramData "Sukoon"
$Database = Join-Path $DataDir "sukoon.db"
$LogFile  = Join-Path $DataDir "restore.log"

function Say([string] $message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Write-Output $line
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction Stop } catch { }
}

trap {
    Say ("FAILED at line {0}: {1}" -f $_.InvocationInfo.ScriptLineNumber, $_.Exception.Message)
    Say "Sukoon's task is left DISABLED so nothing writes to a half-restored database. Fix the cause, then run this again, or re-enable the task."
    exit 20
}

$Backup = (Resolve-Path $Backup).Path
$header = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($Backup), 0, 15)
if ($header -ne "SQLite format 3") { throw "$Backup is not a Sukoon database backup." }
Say "Restore starting from $Backup"

# 1. Stop Sukoon, and stop the watchdog from starting it again halfway through.
Disable-ScheduledTask -TaskName $TaskName | Out-Null
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Get-Process -Name "sukoon-server" -ErrorAction SilentlyContinue | Stop-Process -Force
for ($i = 0; $i -lt 30 -and (Get-Process -Name "sukoon-server" -ErrorAction SilentlyContinue); $i++) { Start-Sleep 1 }
if (Get-Process -Name "sukoon-server" -ErrorAction SilentlyContinue) { throw "Sukoon's server would not stop." }
Say "Sukoon stopped."

# 2. Keep the current database — with its -wal file, which can hold the most recent sales.
$keep = Join-Path $DataDir ("backups\before-restore-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Force -Path $keep | Out-Null
foreach ($suffix in "", "-wal", "-shm") {
    if (Test-Path "$Database$suffix") { Copy-Item "$Database$suffix" $keep -Force }
}
Say "Kept the current database in $keep"

# 3. Put the backup in place. The old -wal and -shm belong to the state being replaced; SQLite
#    would replay them on top of the restored file.
Remove-Item "$Database-wal", "$Database-shm" -ErrorAction SilentlyContinue
Copy-Item $Backup "$Database.restoring" -Force
Move-Item "$Database.restoring" $Database -Force
& icacls $Database /reset /C /Q | Out-Null   # inherit the data folder's permissions (ADR-0036)
Say "Backup put in place."

# 4. Start Sukoon again and make sure it answers.
Enable-ScheduledTask -TaskName $TaskName | Out-Null
Start-ScheduledTask -TaskName $TaskName
$answered = $false
for ($i = 0; $i -lt 90 -and -not $answered; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/static/css/tailwind.css" -TimeoutSec 2 -ErrorAction Stop | Out-Null
        $answered = $true
    } catch { Start-Sleep 1 }
}
if (-not $answered) { throw "Sukoon did not answer after the restore. Its log is $DataDir\logs\sukoon.log" }
Say "Restore finished. Sukoon is answering. To undo it, restore from $keep\sukoon.db"
exit 0

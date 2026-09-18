<#
Removes Sukoon's server from the shop PC. Run by the uninstaller, as Administrator.

KEEPS the shop's data in C:\ProgramData\Sukoon\ (ADR-0036 section 3): uninstalling Sukoon must never
take the books with it. Removing that folder is a separate, deliberate act.
#>
$ErrorActionPreference = "Continue"
$Account  = "SukoonService"
$TaskName = "Sukoon Server"
$DataDir  = Join-Path $env:ProgramData "Sukoon"
$LogFile  = Join-Path $DataDir "install.log"

function Say([string] $message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Write-Output $line
    if (Test-Path $DataDir) { Add-Content -Path $LogFile -Value $line -Encoding UTF8 }
}

Say "Sukoon uninstall starting."
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Say "Removed the '$TaskName' task."
}
Get-Process -Name "sukoon-server", "Sukoon" -ErrorAction SilentlyContinue | Stop-Process -Force
# Stop-Process returns before Windows releases the files, and the uninstaller starts deleting
# immediately: the first real uninstall left sukoon-server.exe behind (VM, 2026-09-18).
for ($i = 0; $i -lt 30; $i++) {
    if (-not (Get-Process -Name "sukoon-server", "Sukoon" -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
}
Start-Sleep -Seconds 2   # the handles close a moment after the process does
Get-NetFirewallRule -DisplayName "Sukoon" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Say "Removed the firewall rule."
if (Get-LocalUser -Name $Account -ErrorAction SilentlyContinue) {
    Remove-LocalUser -Name $Account
    Say "Removed the $Account account."
}
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList" `
    -Name $Account -ErrorAction SilentlyContinue
Say "Uninstall finished. The shop's data was kept in $DataDir."
exit 0

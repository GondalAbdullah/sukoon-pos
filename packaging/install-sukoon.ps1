<#
Sets up Sukoon's server on the shop PC. Run by the installer, as Administrator.

  ADR-0035  the server starts at boot as a task under a dedicated account with a stored password
            (a passwordless task could not read the WhatsApp key: measured, 0x5)
  ADR-0036  data in C:\ProgramData\Sukoon\, writable by that account, readable by no ordinary user
  ADR-0038  firewall open on private networks only; the tills reach Sukoon over the shop's LAN

Safe to run again. An UPGRADE leaves the account, its password and the task exactly as they are:
the WhatsApp key is encrypted for that account, and giving it a new password would make the saved
key unreadable (ADR-0035 section 4). Only the program files change.

Written for Windows PowerShell 5.1, which every supported Windows has. Accounts and groups are named
by their built-in IDs, not English names, so this works on a Windows installed in any language.
#>
param(
    [Parameter(Mandatory = $true)] [string] $AppDir,
    [int] $Port = 5000,
    # A silent install has nobody to click OK: without this the problem dialog would hang it.
    [switch] $Quiet
)

$ErrorActionPreference = "Stop"
$Account  = "SukoonService"
$TaskName = "Sukoon Server"
$RuleName = "Sukoon"
$DataDir  = Join-Path $env:ProgramData "Sukoon"
$Server   = Join-Path $AppDir "sukoon-server.exe"
$LogFile  = Join-Path $DataDir "install.log"
$Problems = New-Object System.Collections.Generic.List[string]

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

# Exit codes. PowerShell's own failure exit is 1, so "finished, with problems" must not be 1: the
# first install crashed, exited 1, and the installer took it for a warning.
$ExitDone     = 0
$ExitProblems = 10
$ExitFailed   = 20

function Say([string] $message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Write-Output $line
    # Logging must never be what stops the set-up.
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction Stop } catch { }
}

function New-StrongPassword {
    # Nobody types this. It exists so Windows can log the task on with a password, which is what
    # unlocks the account's encryption keys (ADR-0035). Base64 of 24 random bytes plus a symbol
    # meets any Windows complexity policy.
    $bytes = New-Object byte[] 24
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return "Sk!" + [Convert]::ToBase64String($bytes)
}

# Any error stops the script, and must leave its reason in the log: the first real install died on a
# 48-character limit and the installer still reported success, with nothing written anywhere.
trap {
    Say ("FAILED at line {0}: {1}" -f $_.InvocationInfo.ScriptLineNumber, $_.Exception.Message)
    exit $ExitFailed
}

function Test-BatchLogonRight([string] $Sid) {
    # secedit lists groups as *SID but a local user by NAME ("SukoonService,*S-1-5-32-544,..."), so
    # every entry is translated to a SID before comparing. Comparing SIDs as text alone reported a
    # successful grant as a failure.
    $cfg = Join-Path $env:TEMP "sukoon-rights-check.inf"
    & secedit /export /cfg $cfg /areas USER_RIGHTS /quiet | Out-Null
    $line = @(Get-Content -Path $cfg) | Where-Object { $_ -match '^SeBatchLogonRight\s*=' } | Select-Object -First 1
    Remove-Item $cfg -ErrorAction SilentlyContinue
    if (-not $line) { return $false }
    foreach ($entry in (($line -split '=', 2)[1] -split ',')) {
        $entry = $entry.Trim()
        if ($entry.StartsWith('*')) { $entrySid = $entry.Substring(1) }
        else {
            try { $entrySid = (New-Object Security.Principal.NTAccount($entry)).Translate(
                    [Security.Principal.SecurityIdentifier]).Value } catch { continue }
        }
        if ($entrySid -eq $Sid) { return $true }
    }
    return $false
}

function Grant-BatchLogonRight([string] $Sid) {
    # A task that runs "whether the user is logged on or not" with a stored password needs its
    # account to hold "Log on as a batch job". Registering the task through PowerShell does NOT grant
    # it: the first real install registered the task, Task Scheduler "attempted to run" it, and it
    # never ran — no process, no log, last result 0x41303 "has not yet run" — because the account
    # could not log on. secedit is on every Windows edition, Home included.
    if (Test-BatchLogonRight $Sid) { return $false }
    $cfg = Join-Path $env:TEMP "sukoon-rights.inf"
    $db  = Join-Path $env:TEMP "sukoon-rights.sdb"
    & secedit /export /cfg $cfg /areas USER_RIGHTS /quiet | Out-Null
    $lines = @(Get-Content -Path $cfg)
    if ($lines | Where-Object { $_ -match '^SeBatchLogonRight\s*=' }) {
        $lines = $lines | ForEach-Object { if ($_ -match '^SeBatchLogonRight\s*=') { "$_,*$Sid" } else { $_ } }
    } else {
        $lines = $lines | ForEach-Object { $_; if ($_ -eq '[Privilege Rights]') { "SeBatchLogonRight = *$Sid" } }
    }
    Set-Content -Path $cfg -Value $lines -Encoding Unicode
    & secedit /configure /db $db /cfg $cfg /areas USER_RIGHTS /quiet | Out-Null
    $code = $LASTEXITCODE
    Remove-Item $cfg, $db -ErrorAction SilentlyContinue
    if ($code -ne 0) { throw "Granting the Sukoon account 'Log on as a batch job' failed (secedit exit $code)." }
    if (-not (Test-BatchLogonRight $Sid)) {   # check, don't assume
        throw "secedit reported success but the Sukoon account still cannot log on as a batch job."
    }
    return $true
}

Say "Sukoon setup starting. Program: $AppDir  Data: $DataDir  Port: $Port"

# --- 1. The account and the boot task (ADR-0035) ----------------------------------------------
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$user = Get-LocalUser -Name $Account -ErrorAction SilentlyContinue
$qualified = "$env:COMPUTERNAME\$Account"

if ($task -and $user) {
    Say "Upgrade: the $Account account and the '$TaskName' task already exist and are left unchanged."
    Enable-ScheduledTask -TaskName $TaskName | Out-Null   # the installer paused it for the upgrade
} else {
    $plain  = New-StrongPassword
    $secure = ConvertTo-SecureString $plain -AsPlainText -Force
    if ($user) {
        # An earlier install got as far as the account but not the task. Nothing can have been
        # encrypted for it yet, so a new password loses nothing.
        Set-LocalUser -Name $Account -Password $secure
        Say "The $Account account existed without its task; gave it a new password."
    } else {
        New-LocalUser -Name $Account -Password $secure -PasswordNeverExpires `
            -UserMayNotChangePassword -AccountNeverExpires `
            -Description "Runs the Sukoon server (Sukoon installer)" | Out-Null  # Windows allows 48 characters
        Say "Created the $Account account."
    }
    # Not a login anyone uses: keep it off the sign-in screen.
    $hide = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList"
    New-Item -Path $hide -Force | Out-Null
    New-ItemProperty -Path $hide -Name $Account -Value 0 -PropertyType DWord -Force | Out-Null
}

# Every run, upgrades included: without this right the task silently never starts.
$sid = (Get-LocalUser -Name $Account).SID.Value
if (Grant-BatchLogonRight $sid) { Say "Granted $Account 'Log on as a batch job'." }
else { Say "$Account already holds 'Log on as a batch job'." }

# --- 2. The data folder (ADR-0036) ---------------------------------------------------------------
# SYSTEM (S-1-5-18) and Administrators (S-1-5-32-544) full control, the Sukoon account modify,
# nobody else — set on the FOLDER, and everything inside made to inherit it.
#
# Not "/grant ... /T": that applies the folder's (OI)(CI) grants to each file too, where those flags
# mean nothing, and strips the file's inherited access at the same time. The first real install
# left install.log with no permissions at all — readable by nobody. On an upgrade it would have done
# the same to sukoon.db and secret.key, and Sukoon could not have opened its own database.
& icacls $DataDir /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" `
    "${qualified}:(OI)(CI)M" /C /Q | Out-Null
$folderExit = $LASTEXITCODE
& icacls "$DataDir\*" /reset /T /C /Q | Out-Null
$childrenExit = $LASTEXITCODE
if ($folderExit -ne 0 -or $childrenExit -ne 0) {
    throw "Setting the data folder's permissions failed (icacls exit $folderExit / $childrenExit)."
}
Say "Data folder permissions: SYSTEM, Administrators and $Account only; everything inside inherits."

# --- 3. Register the task (new installs only) ---------------------------------------------------
if (-not ($task -and $user)) {
    $action   = New-ScheduledTaskAction -Execute $Server -WorkingDirectory $AppDir
    $atBoot   = New-ScheduledTaskTrigger -AtStartup
    # A watchdog: every five minutes, start the server if it isn't running. IgnoreNew below makes
    # this do nothing while it is.
    $watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
        -RepetitionInterval (New-TimeSpan -Minutes 5)
    # ExecutionTimeLimit zero: Task Scheduler's default stops a task after 72 hours, which would
    # take the shop down every three days.
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($atBoot, $watchdog) `
        -Settings $settings -User $qualified -Password $plain -RunLevel Limited `
        -Description "Serves Sukoon to every till. Starts with Windows; nobody needs to sign in." `
        -Force | Out-Null
    $plain = $null
    Say "Registered the '$TaskName' task: at boot, plus a five-minute watchdog, no time limit."
}

# --- 4. Firewall: the shop's network only (ADR-0038 section 4) ----------------------------------
Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort $Port -Profile Private -Program $Server | Out-Null
Say "Firewall: TCP $Port open to sukoon-server.exe on private networks only."

$public = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object NetworkCategory -eq "Public")
if ($public.Count -gt 0) {
    $names = ($public | ForEach-Object { $_.Name }) -join ", "
    $Problems.Add("This PC's network ($names) is marked Public, so other tills cannot reach Sukoon. " +
        "Set it to Private: Settings > Network & internet > (the network) > Private network.")
}

# --- 5. The window's browser engine (ADR-0038 section 5) ----------------------------------------
$webview2 = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
$found = @("HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$webview2",
           "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$webview2") |
    Where-Object { (Get-ItemProperty -Path $_ -ErrorAction SilentlyContinue).pv }
if (-not $found) {
    $Problems.Add("Microsoft WebView2 is not installed, so the Sukoon window cannot open. " +
        "Sukoon still works in Edge or Chrome at http://localhost:$Port")
} else { Say "WebView2 is installed." }

# --- 6. Start it and make sure it answers ----------------------------------------------------------
Start-ScheduledTask -TaskName $TaskName
$answered = $false
for ($i = 0; $i -lt 90 -and -not $answered; $i++) {
    # The stylesheet: 200 whether or not setup has happened, with no redirect. The first version
    # probed /setup, which redirects once an owner exists — PowerShell 5.1 turns that redirect into
    # an error, and every upgrade reported "Sukoon did not answer" while it was serving fine.
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/static/css/tailwind.css" `
            -TimeoutSec 2 -ErrorAction Stop | Out-Null
        $answered = $true
    } catch {
        Start-Sleep -Seconds 1
    }
}
if ($answered) { Say "Sukoon is answering on port $Port." }
else { $Problems.Add("Sukoon did not answer within 90 seconds. Its log is $DataDir\logs\sukoon.log") }

if ($Problems.Count -gt 0) {
    foreach ($p in $Problems) { Say "PROBLEM: $p" }
    if ($Quiet) { exit $ExitProblems }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "Sukoon is installed, but needs attention:`n`n- " + ($Problems -join "`n`n- ") +
        "`n`nThis list is also saved in $LogFile", "Sukoon setup", "OK", "Warning") | Out-Null
    exit $ExitProblems
}
Say "Sukoon setup finished with no problems."
exit $ExitDone

# Frees local dev ports on Windows by stopping whatever listens on them.
# A `uvicorn --reload` server is a chain of python processes (venv launcher -> reloader -> worker);
# stopping only the port owner can leave the server alive, so this walks up to the top python
# process and stops the whole tree.
param([Parameter(ValueFromRemainingArguments = $true)][int[]]$Ports)
$done = @{}
foreach ($conn in Get-NetTCPConnection -LocalPort $Ports -State Listen -ErrorAction SilentlyContinue) {
    $target = Get-CimInstance Win32_Process -Filter "ProcessId = $($conn.OwningProcess)"
    if (-not $target) { continue }
    while ($true) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($target.ParentProcessId)"
        if ($parent -and $parent.Name -match '^python') { $target = $parent } else { break }
    }
    if ($done[$target.ProcessId]) { continue }
    $done[$target.ProcessId] = $true
    Write-Host "Port $($conn.LocalPort): stopping $($target.Name) (PID $($target.ProcessId))"
    taskkill /PID $target.ProcessId /T /F 2>$null | Out-Null
}

# Dev helper: press a button on Orca's native permission dialogs (MCP cannot answer native modals).
# Usage: tools\press_dialog.ps1 -Title "Plugin permissions" -Button Yes [-Match "192.168"]
param(
    [string]$Title = "Plugin permission",
    [string]$Button = "Yes",
    [string]$Match = "Prusa Integration",
    [int]$Max = 30
)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$proc = Get-Process orca-slicer -ErrorAction Stop
$pressed = 0
for ($i = 0; $i -lt $Max; $i++) {
    # More than one Orca can run (e.g. one stuck closing), so search the windows of each.
    $dialogs = foreach ($id in $proc.Id) {
        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, [int]$id)
        $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
    }
    $dialogs = $dialogs |
        Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Window -and $_.Current.Name -like "$Title*" }
    $target = $null
    foreach ($d in $dialogs) {
        $text = ($d.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition) |
            ForEach-Object { $_.Current.Name }) -join " "
        if ($text -like "*$Match*") {
            $target = $d
            $flat = $text -replace '\s+', ' '
            Write-Output ("[{0}] {1}" -f $d.Current.Name, $flat.Substring(0, [Math]::Min(200, $flat.Length)))
            break
        }
    }
    if (-not $target) { break }
    # Task-dialog buttons show up as panes, so match by name only.
    $btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $Button)
    $btn = $target.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
    if (-not $btn) { Write-Output "no '$Button' button"; break }
    $invoke = $null
    if ($btn.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invoke)) {
        $invoke.Invoke()
    } else {
        $btn.SetFocus()
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.SendKeys]::SendWait(" ")
    }
    $pressed++
    Start-Sleep -Milliseconds 700
}
Write-Output "pressed $pressed"

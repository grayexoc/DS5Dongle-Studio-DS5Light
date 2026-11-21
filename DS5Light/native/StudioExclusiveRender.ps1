$ErrorActionPreference = 'Stop'
Add-Type -Path "$PSScriptRoot/StudioExclusiveRender.cs"
[Console]::WriteLine('READY')
[Console]::Out.Flush()
if ([Console]::ReadLine() -eq 'GO') {
    try { [ExclusiveProbe]::Run($args[0], $args.Count -gt 1 -and $args[1] -eq "live") }
    catch {
        [Console]::WriteLine($_.Exception.GetBaseException().Message)
        exit 1
    }
}


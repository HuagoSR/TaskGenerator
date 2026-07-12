param(
    [Parameter(Mandatory=$true)][string]$InputDocx,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [Parameter(Mandatory=$true)][string]$PdfToPpmExe
)
$ErrorActionPreference = 'Stop'
$inputPath = (Resolve-Path -LiteralPath $InputDocx).Path
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$outputPath = (Resolve-Path -LiteralPath $OutputDir).Path
$pdfPath = Join-Path $outputPath (([IO.Path]::GetFileNameWithoutExtension($inputPath)) + '.pdf')
$before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$job = Start-Job -ScriptBlock {
    param($inputPath, $pdfPath)
    $word = $null
    $document = $null
    try {
        $word = New-Object -ComObject Word.Application
        $word.Visible = $false
        $word.DisplayAlerts = 0
        $document = $word.Documents.Open($inputPath, $false, $true)
        $document.SaveAs2($pdfPath, 17)
    } finally {
        if ($null -ne $document) { $document.Close($false) }
        if ($null -ne $word) { $word.Quit() }
    }
} -ArgumentList $inputPath, $pdfPath
if (-not (Wait-Job $job -Timeout 60)) {
    Stop-Job $job
    $after = Get-Process WINWORD -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id }
    $after | Stop-Process -Force
    Remove-Job $job -Force
    throw 'Word COM PDF conversion timed out after 60 seconds.'
}
Receive-Job $job
Remove-Job $job -Force
& $PdfToPpmExe -png -r 150 $pdfPath (Join-Path $outputPath 'page')
if ($LASTEXITCODE -ne 0) { throw "pdftoppm failed with exit code $LASTEXITCODE" }

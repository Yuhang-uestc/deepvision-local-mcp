param(
    [Parameter(Mandatory = $true)][string]$ImagePath,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [string]$Lang = "zh-Hans-CN"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null

[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($WinRtTask, $ResultType) {
    try {
        $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
        $netTask = $asTask.Invoke($null, @($WinRtTask))
        $netTask.Wait(-1) | Out-Null
        $netTask.Result
    } catch {
        $ex = $_.Exception
        $depth = 0
        while ($ex.InnerException -and $depth -lt 10) {
            $ex = $ex.InnerException
            $depth++
        }
        throw "Await($ResultType) failed: $($ex.Message)"
    }
}

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language $Lang))
if (-not $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}
if (-not $engine) {
    throw "No OCR engine available for language: $Lang"
}

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

$lines = @()
foreach ($line in $result.Lines) {
    $lb = $line.BoundingRect
    $words = @()
    foreach ($word in $line.Words) {
        $wb = $word.BoundingRect
        $words += [PSCustomObject]@{
            text = $word.Text
            x = [math]::Round($wb.X)
            y = [math]::Round($wb.Y)
            w = [math]::Round($wb.Width)
            h = [math]::Round($wb.Height)
        }
    }
    $lines += [PSCustomObject]@{
        text = $line.Text
        x = [math]::Round($lb.X)
        y = [math]::Round($lb.Y)
        w = [math]::Round($lb.Width)
        h = [math]::Round($lb.Height)
        words = $words
    }
}

[PSCustomObject]@{
    language = $engine.RecognizerLanguage.LanguageTag
    text     = $result.Text
    lines    = $lines
} | ConvertTo-Json -Depth 5 | Out-File -FilePath $OutFile -Encoding utf8

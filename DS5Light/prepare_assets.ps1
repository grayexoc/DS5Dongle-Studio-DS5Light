$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

# Generate only the fixed-size display asset; retain the supplied original.
$ds5SourcePath = Join-Path $PSScriptRoot 'assets/source/brand-mark.png'
$ds5DisplayPath = Join-Path $PSScriptRoot 'assets/brand-mark.png'
$ds5Size = 64
$ds5SourceImage = [System.Drawing.Image]::FromFile($ds5SourcePath)
$ds5DisplayImage = [System.Drawing.Bitmap]::new($ds5Size, $ds5Size, [System.Drawing.Imaging.PixelFormat]::Format32bppPArgb)
$ds5Graphics = $null
$ds5ImageAttributes = $null
try {
    $ds5DisplayImage.SetResolution(96, 96)
    $ds5Graphics = [System.Drawing.Graphics]::FromImage($ds5DisplayImage)
    $ds5Graphics.Clear([System.Drawing.Color]::Transparent)
    $ds5Graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
    $ds5Graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $ds5Graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $ds5Graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $ds5ImageAttributes = [System.Drawing.Imaging.ImageAttributes]::new()
    $ds5ImageAttributes.SetWrapMode([System.Drawing.Drawing2D.WrapMode]::TileFlipXY)
    $ds5Scale = [Math]::Min($ds5Size / $ds5SourceImage.Width, $ds5Size / $ds5SourceImage.Height)
    $ds5Width = [Math]::Max(1, [int][Math]::Round($ds5SourceImage.Width * $ds5Scale))
    $ds5Height = [Math]::Max(1, [int][Math]::Round($ds5SourceImage.Height * $ds5Scale))
    $ds5Rectangle = [System.Drawing.Rectangle]::new([int][Math]::Floor(($ds5Size-$ds5Width)/2), [int][Math]::Floor(($ds5Size-$ds5Height)/2), $ds5Width, $ds5Height)
    $ds5Graphics.DrawImage($ds5SourceImage, $ds5Rectangle, 0, 0, $ds5SourceImage.Width, $ds5SourceImage.Height, [System.Drawing.GraphicsUnit]::Pixel, $ds5ImageAttributes)
    $ds5DisplayImage.Save($ds5DisplayPath, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    if ($ds5ImageAttributes) { $ds5ImageAttributes.Dispose() }
    if ($ds5Graphics) { $ds5Graphics.Dispose() }
    $ds5DisplayImage.Dispose()
    $ds5SourceImage.Dispose()
}

# Precompute a few high-quality watermark sizes; no runtime image library or
# per-frame resampling. Preserve the source's alpha and original proportions.
$ds5DiagnosticSource = [System.Drawing.Image]::FromFile((Join-Path $PSScriptRoot 'assets/source/diagnostic-bg.png'))
try {
    foreach ($ds5DiagnosticWidth in @(120,160,240,320)) {
        $ds5DiagnosticDisplayWidth = [int]($ds5DiagnosticWidth * 1.5)
        $ds5DiagnosticHeight = [int][Math]::Round($ds5DiagnosticDisplayWidth * $ds5DiagnosticSource.Height / $ds5DiagnosticSource.Width)
        $ds5DiagnosticBitmap = [System.Drawing.Bitmap]::new($ds5DiagnosticDisplayWidth,$ds5DiagnosticHeight,[System.Drawing.Imaging.PixelFormat]::Format32bppPArgb)
        $ds5DiagnosticGraphics = [System.Drawing.Graphics]::FromImage($ds5DiagnosticBitmap)
        $ds5DiagnosticAttributes = [System.Drawing.Imaging.ImageAttributes]::new()
        try {
            $ds5DiagnosticGraphics.Clear([System.Drawing.Color]::Transparent)
            $ds5DiagnosticGraphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $ds5DiagnosticGraphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $ds5DiagnosticGraphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
            $ds5DiagnosticAttributes.SetWrapMode([System.Drawing.Drawing2D.WrapMode]::TileFlipXY)
            $ds5DiagnosticMatrix = [System.Drawing.Imaging.ColorMatrix]::new()
            $ds5DiagnosticMatrix.Matrix33 = 0.45
            $ds5DiagnosticAttributes.SetColorMatrix($ds5DiagnosticMatrix)
            $ds5DiagnosticRect = [System.Drawing.Rectangle]::new(0,0,$ds5DiagnosticDisplayWidth,$ds5DiagnosticHeight)
            $ds5DiagnosticGraphics.DrawImage($ds5DiagnosticSource,$ds5DiagnosticRect,0,0,$ds5DiagnosticSource.Width,$ds5DiagnosticSource.Height,[System.Drawing.GraphicsUnit]::Pixel,$ds5DiagnosticAttributes)
            $ds5DiagnosticBitmap.Save((Join-Path $PSScriptRoot "assets/diagnostic-bg-$ds5DiagnosticWidth.png"),[System.Drawing.Imaging.ImageFormat]::Png)
        } finally {
            $ds5DiagnosticAttributes.Dispose()
            $ds5DiagnosticGraphics.Dispose()
            $ds5DiagnosticBitmap.Dispose()
        }
    }
} finally {
    $ds5DiagnosticSource.Dispose()
}

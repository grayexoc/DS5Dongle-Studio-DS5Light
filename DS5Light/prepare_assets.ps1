$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

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

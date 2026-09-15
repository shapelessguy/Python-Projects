param($name)
Add-Type -AssemblyName System.Drawing
$src = "C:\Users\shape\Documents\codebase\sharedCode\CyanHouse\android_ui\$name.png"
$dst = "C:\Users\shape\Documents\codebase\sharedCode\CyanHouse\android_ui\${name}_s.png"
$img = [System.Drawing.Image]::FromFile($src)
$ratio = [Math]::Min(1200.0/$img.Width, 1200.0/$img.Height)
$w = [int]($img.Width*$ratio); $h = [int]($img.Height*$ratio)
$bmp = New-Object System.Drawing.Bitmap $w,$h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.DrawImage($img,0,0,$w,$h)
$bmp.Save($dst,[System.Drawing.Imaging.ImageFormat]::Png)
$img.Dispose(); $bmp.Dispose(); $g.Dispose()

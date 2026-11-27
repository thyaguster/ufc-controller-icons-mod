$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Push-Location -LiteralPath $root
try {
    $vendor = Join-Path $root 'vendor/xbox-icons'
    $ufc3Src = Join-Path $root 'ufc3/src'
    $ufc4Src = Join-Path $root 'ufc4/src'
    $ufc4Kb = Join-Path $root 'ufc4/src/ufc4_keyboard'
    $font = Join-Path $ufc4Kb 'keyboard-art/font/BarlowCondensed-Bold.ttf'
    $kenneyZip = Join-Path $ufc4Kb 'keyboard-art/kenney_kb_prompts.zip'
    $tail = Join-Path $ufc4Src 'ufc4_buttonart_xbox_tail.bin'
    $ufc4Zip = Join-Path $ufc4Src 'ufc4_xbox_gnf.zip'
    $ufc23Zip = Join-Path $ufc3Src 'ufc23_xbox_gnf.zip'
    $gamepadZip = Join-Path $root 'installer/kenney_gamepad_prompts.zip'
    $icon = Join-Path $root 'installer/assets/overlay.ico'

    & python -m PyInstaller --noconfirm --clean --onefile --windowed `
        --exclude-module numpy --exclude-module tkinter --exclude-module _tkinter `
        --exclude-module cryptography --exclude-module bcrypt --exclude-module pygments `
        --exclude-module setuptools --exclude-module mako --exclude-module wheel `
        --icon "$icon" `
        --name UFC_Controller_Icons_Mod_WebView2 `
        --distpath dist `
        --workpath .build/webview-icons-build `
        --specpath .build/webview-icons-spec `
        --paths "$root/installer" --paths "$ufc3Src" --paths "$ufc4Src" --paths "$ufc4Kb" --paths "$vendor" `
        --add-data "$vendor/profiles;profiles" `
        --add-data "$vendor/keyboard-art;keyboard-art" `
        --add-data "$font;ufc4_keyboard/keyboard-art/font" `
        --add-data "$kenneyZip;ufc4_keyboard/keyboard-art" `
        --add-data "$tail;." `
        --add-data "$ufc4Zip;." `
        --add-data "$ufc23Zip;." `
        --add-data "$gamepadZip;." `
        --add-data "$icon;." `
        installer/ufc_icons_webview.py
    if ($LASTEXITCODE) { throw 'WebView2 icons installer build failed' }
    Write-Host 'Built dist/UFC_Controller_Icons_Mod_WebView2.exe'
}
finally {
    Pop-Location
}

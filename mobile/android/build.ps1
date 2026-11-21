param(
    [Parameter(Mandatory = $true)][string]$SdkRoot,
    [Parameter(Mandatory = $true)][string]$JavaHome
)

$ErrorActionPreference = 'Stop'
$SdkRoot = (Resolve-Path -LiteralPath $SdkRoot).Path
$env:JAVA_HOME = (Resolve-Path -LiteralPath $JavaHome).Path
$tools = Join-Path $SdkRoot 'build-tools/35.0.0'
$androidJar = Join-Path $SdkRoot 'platforms/android-35/android.jar'
$web = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../web')).Path
if (-not (Test-Path -LiteralPath (Join-Path $web 'index.html') -PathType Leaf)) {
    throw 'mobile/web/index.html is required.'
}

function Invoke-AndroidTool {
    param([string]$Program)
    & $Program @args
    if ($LASTEXITCODE -ne 0) {
        throw "$Program exited with code $LASTEXITCODE."
    }
}

Invoke-AndroidTool python "$PSScriptRoot/../prepare_vision_assets.py"

$buildRoot = (New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot '../build')).FullName
$stage = (New-Item -ItemType Directory (Join-Path $buildRoot ([Guid]::NewGuid().ToString()))).FullName
try {
    Invoke-AndroidTool "$env:JAVA_HOME/bin/javac.exe" -encoding UTF-8 --release 8 -classpath $androidJar -d $stage "$PSScriptRoot/MainActivity.java"
    $classes = @(Get-ChildItem -LiteralPath $stage -Recurse -Filter '*.class' | ForEach-Object FullName)
    Invoke-AndroidTool "$tools/d8.bat" --lib $androidJar --min-api 26 --output $stage @classes
    New-Item -ItemType Directory "$stage/drawable-xxxhdpi" | Out-Null
    Copy-Item -LiteralPath "$web/icon-192.png" -Destination "$stage/drawable-xxxhdpi/app_icon.png"
    Invoke-AndroidTool "$tools/aapt2.exe" compile (Join-Path $stage 'drawable-xxxhdpi/app_icon.png') -o $stage
    Invoke-AndroidTool "$tools/aapt2.exe" link -I $androidJar --manifest "$PSScriptRoot/AndroidManifest.xml" -o "$stage/assets.apk" "$stage/drawable-xxxhdpi_app_icon.png.flat"

    $files = @(Get-ChildItem -LiteralPath $web -Recurse -File -Force)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::Open("$stage/assets.apk", [IO.Compression.ZipArchiveMode]::Update)
    try {
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, "$stage/classes.dex", 'classes.dex')
        # AAPT2 on Windows emits backslashes for nested assets, which AssetManager cannot resolve.
        foreach ($file in $files) {
            $name = $file.FullName.Substring($web.Length + 1).Replace('\', '/')
            [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file.FullName, "assets/$name")
        }
    } finally {
        $archive.Dispose()
    }
    Invoke-AndroidTool "$tools/zipalign.exe" -f 4 "$stage/assets.apk" "$stage/aligned.apk"

    $key = Join-Path $SdkRoot 'eyeseeyou-local-test.jks'
    if (-not (Test-Path -LiteralPath $key -PathType Leaf)) {
        Invoke-AndroidTool "$env:JAVA_HOME/bin/keytool.exe" -genkeypair -keystore $key -storepass android -keypass android -alias eyeseeyou -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=EyeSeeYou Edge Local Test'
    }
    Invoke-AndroidTool "$tools/apksigner.bat" sign --ks $key --ks-key-alias eyeseeyou --ks-pass pass:android --key-pass pass:android --v4-signing-enabled false --out "$stage/signed.apk" "$stage/aligned.apk"
    Invoke-AndroidTool "$tools/apksigner.bat" verify --verbose "$stage/signed.apk"
    Invoke-AndroidTool "$tools/zipalign.exe" -c 4 "$stage/signed.apk"

    $archive = [IO.Compression.ZipFile]::OpenRead("$stage/signed.apk")
    try {
        $assets = @($archive.Entries | Where-Object FullName -like 'assets/*')
        if ($files.Length -ne $assets.Length -or -not $archive.GetEntry('classes.dex')) {
            throw 'APK asset count or executable entry is incorrect.'
        }
        foreach ($file in $files) {
            $name = $file.FullName.Substring($web.Length + 1).Replace('\', '/')
            $entry = $archive.GetEntry("assets/$name")
            if (-not $entry) {
                throw "APK asset missing: $name"
            }
            $content = $entry.Open()
            try {
                if ((Get-FileHash -InputStream $content).Hash -ne (Get-FileHash -LiteralPath $file.FullName).Hash) {
                    throw "APK asset differs from source: $name"
                }
            } finally {
                $content.Dispose()
            }
        }
    } finally {
        $archive.Dispose()
    }

    $dist = (New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot '../dist')).FullName
    $apk = Join-Path $dist 'EyeSeeYou-Edge-0.3.0-Android.apk'
    Move-Item -LiteralPath "$stage/signed.apk" -Destination $apk -Force
    Get-FileHash -LiteralPath $apk
} finally {
    if ($stage.StartsWith($buildRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}

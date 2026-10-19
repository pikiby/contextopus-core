# Bootstrap the reviewed starter bundle with the official uv installer.
$ErrorActionPreference = 'Stop'
$starterArguments = @($args)
$starterPlan = $starterArguments -contains '--plan'
$starterYes = $starterArguments -contains '--yes'
$starterScript = Join-Path $PSScriptRoot 'install.py'

if ($starterPlan) {
    foreach ($starterPython in @('python', 'python3')) {
        if (Get-Command $starterPython -ErrorAction SilentlyContinue) {
            & $starterPython -c 'import sys; sys.exit(sys.version_info < (3, 12))'
            if ($LASTEXITCODE -eq 0) {
                & $starterPython -B $starterScript @starterArguments
                exit $LASTEXITCODE
            }
        }
    }
    throw 'Preview requires an existing Python 3.12+. Nothing was installed.'
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $starterUvDir = Join-Path $env:USERPROFILE '.local\bin'
    $starterUv = Join-Path $starterUvDir 'uv.exe'
    if (-not (Test-Path -LiteralPath $starterUv)) {
        Write-Host 'Contextopus needs uv to install Python and application dependencies.'
        Write-Host 'Download uv 0.13.1 from https://astral.sh/uv/0.13.1/install.ps1?'
        if (-not $starterYes) {
            $starterAnswer = Read-Host "Install uv in $starterUvDir without changing shell profiles? [y/N]"
            if ($starterAnswer -notin @('y', 'Y', 'yes', 'YES')) { exit 1 }
        }
        $starterDownload = Join-Path ([IO.Path]::GetTempPath()) (([Guid]::NewGuid().ToString()) + '.ps1')
        $starterOldDir = $env:UV_INSTALL_DIR
        $starterOldNoPath = $env:UV_NO_MODIFY_PATH
        try {
            Invoke-WebRequest -Uri 'https://astral.sh/uv/0.13.1/install.ps1' -OutFile $starterDownload -UseBasicParsing
            $env:UV_INSTALL_DIR = $starterUvDir
            $env:UV_NO_MODIFY_PATH = '1'
            & $starterDownload
            if (-not (Test-Path -LiteralPath $starterUv)) { throw 'uv installation did not produce uv.exe.' }
        } finally {
            $env:UV_INSTALL_DIR = $starterOldDir
            $env:UV_NO_MODIFY_PATH = $starterOldNoPath
            Remove-Item -LiteralPath $starterDownload -ErrorAction SilentlyContinue
        }
    }
    $env:PATH = "$starterUvDir;$env:PATH"
}

& uv run --no-project --no-config --python 3.12 python -B $starterScript @starterArguments
exit $LASTEXITCODE

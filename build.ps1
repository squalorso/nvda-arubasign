# Crea il pacchetto .nvda-addon a partire dalla cartella addon\.
# Uso: .\build.ps1
$ErrorActionPreference = "Stop"
$radice = $PSScriptRoot
$manifest = Get-Content (Join-Path $radice "addon\manifest.ini") -Raw
if ($manifest -match 'version\s*=\s*(\S+)') { $versione = $Matches[1] } else { $versione = "0.0.0" }
$dist = Join-Path $radice "dist"
New-Item -ItemType Directory -Force $dist | Out-Null
$zip = Join-Path $dist "arubaSignCampiFirma-$versione.zip"
$pacchetto = Join-Path $dist "arubaSignCampiFirma-$versione.nvda-addon"
Remove-Item $zip, $pacchetto -Force -ErrorAction SilentlyContinue
# Il contenuto della cartella addon\ va alla radice dello zip (manifest.ini in cima).
# Voci create una a una per garantire separatori "/" standard nei nomi.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$cartellaAddon = Join-Path $radice "addon"
$archivio = [System.IO.Compression.ZipFile]::Open($zip, "Create")
try {
    foreach ($file in Get-ChildItem $cartellaAddon -Recurse -File) {
        $nomeVoce = $file.FullName.Substring($cartellaAddon.Length + 1).Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archivio, $file.FullName, $nomeVoce) | Out-Null
    }
} finally {
    $archivio.Dispose()
}
Rename-Item $zip $pacchetto
Write-Output "Pacchetto creato: $pacchetto"

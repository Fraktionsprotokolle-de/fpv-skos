$ErrorActionPreference = "Stop"

Write-Output "Starte Validierung ..."

python .\scripts\validate_fpv.py

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Output "Validierung erfolgreich."
exit 0
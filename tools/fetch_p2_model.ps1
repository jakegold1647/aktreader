# Owner-only fetch of the P2 baseline model pair.
# This is provisioning, not an AKTREADER inference path. Run from an ordinary PowerShell
# session only after reviewing the revision-pinned URLs and hashes below.

$ErrorActionPreference = 'Stop'
$modelDirectory = 'E:\DNA\Project_RegisterReader\models\qwen3.5-9b-q5_k_m'
New-Item -ItemType Directory -Force -Path $modelDirectory | Out-Null
$artifacts = @(
  @{
    Url = 'https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/9f870da1e1c96da710c13926d36c6946bb7ebb38/Qwen3.5-9B-Q5_K_M.gguf'
    Filename = 'Qwen3.5-9B-Q5_K_M.gguf'
    Sha256 = 'dc2a39aef291f91a9116ad214058da0d86eb648743a124bd8c333787c4b9c91c'
    Bytes = 6577841376
  },
  @{
    Url = 'https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/9f870da1e1c96da710c13926d36c6946bb7ebb38/mmproj-F16.gguf'
    Filename = 'mmproj-F16.gguf'
    Sha256 = 'f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f'
    Bytes = 918166080
  }
)

foreach ($artifact in $artifacts) {
  $destination = Join-Path $modelDirectory $artifact.Filename
  if (Test-Path -LiteralPath $destination -PathType Leaf) {
    $existingBytes = (Get-Item -LiteralPath $destination).Length
    $existingHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($existingBytes -ne $artifact.Bytes -or $existingHash -ne $artifact.Sha256) {
      throw "Existing artifact fails its pin and was left untouched: $destination"
    }
    Write-Host "VERIFIED existing $($artifact.Filename)" -ForegroundColor Green
    continue
  }

  $partial = "$destination.partial"
  Write-Host "Downloading owner-provisioned artifact: $($artifact.Filename)"
  & curl.exe --fail --location --retry 3 --retry-all-errors --retry-delay 10 `
    --output $partial $artifact.Url
  if ($LASTEXITCODE -ne 0) {
    throw "curl failed with exit code $LASTEXITCODE; partial file retained: $partial"
  }

  $observedBytes = (Get-Item -LiteralPath $partial).Length
  $observedHash = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($observedBytes -ne $artifact.Bytes -or $observedHash -ne $artifact.Sha256) {
    throw "Downloaded artifact failed its pin; partial file retained and will not be used: $partial"
  }
  Move-Item -LiteralPath $partial -Destination $destination
  Write-Host "VERIFIED $($artifact.Filename)" -ForegroundColor Green
}

Write-Host "Both artifacts verified. Baseline is ready for msg-003 section 4." -ForegroundColor Green

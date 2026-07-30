# Owner-only provisioning for license-reviewed open training datasets.
# AKTREADER never calls this script and never downloads training data during inference.

[CmdletBinding()]
param(
  [string]$ManifestPath,
  [string]$DestinationRoot,
  [string[]]$DatasetId,
  [switch]$ListOnly,
  [switch]$AcceptLicenses
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
  $invokedScriptPath = [string]$MyInvocation.MyCommand.Path
  if ([string]::IsNullOrWhiteSpace($invokedScriptPath)) {
    throw 'Cannot resolve the default manifest path because the script invocation path is empty.'
  }
  $scriptDirectory = Split-Path -Parent $invokedScriptPath
  $ManifestPath = Join-Path $scriptDirectory '..\resources\open_datasets.manifest.json'
}$Sha256Pattern = '^[a-f0-9]{64}$'
$DatasetIdPattern = '^[a-z0-9][a-z0-9-]{1,62}$'
$ForbiddenUrlFragments = @(
  'yadvashem',
  'ushmm',
  'arolsen',
  'geneteka',
  'jri-poland',
  'jewishgen'
)

function Get-LowerSha256 {
  param([Parameter(Mandatory = $true)][string]$Path)
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-LeafFilename {
  param([Parameter(Mandatory = $true)][string]$Filename)
  if ([string]::IsNullOrWhiteSpace($Filename) -or
      [System.IO.Path]::GetFileName($Filename) -ne $Filename -or
      $Filename -in @('.', '..')) {
    throw "Artifact filename must be one safe leaf name: $Filename"
  }
}

function Assert-EligibleUrl {
  param([Parameter(Mandatory = $true)][string]$Url)
  $uri = $null
  if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri) -or
      $uri.Scheme -ne 'https') {
    throw "Dataset artifact URL must be absolute HTTPS: $Url"
  }
  $normalized = $Url.ToLowerInvariant()
  foreach ($fragment in $ForbiddenUrlFragments) {
    if ($normalized.Contains($fragment)) {
      throw "Standing-excluded source fragment '$fragment' appears in eligible URL: $Url"
    }
  }
}

function Write-AtomicJson {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)]$Payload
  )
  $partial = "$Path.partial"
  $json = $Payload | ConvertTo-Json -Depth 30
  [System.IO.File]::WriteAllText(
    $partial,
    $json + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
  )
  Move-Item -LiteralPath $partial -Destination $Path -Force
}

$resolvedManifest = (Resolve-Path -LiteralPath $ManifestPath).Path
$manifest = Get-Content -Raw -LiteralPath $resolvedManifest | ConvertFrom-Json
if ($manifest.schema_version -ne '1.0.0') {
  throw "Unsupported open-dataset manifest schema: $($manifest.schema_version)"
}
if ($manifest.owner_execution_only -ne $true -or
    $manifest.application_downloads_datasets -ne $false) {
  throw 'Manifest must remain owner-executed and disconnected from application downloads.'
}

$datasets = @($manifest.datasets)
if ($datasets.Count -eq 0) {
  throw 'Manifest contains no eligible datasets.'
}
$seenDatasetIds = @{}
foreach ($dataset in $datasets) {
  if ($dataset.id -notmatch $DatasetIdPattern) {
    throw "Unsafe dataset id: $($dataset.id)"
  }
  if ($seenDatasetIds.ContainsKey($dataset.id)) {
    throw "Duplicate dataset id: $($dataset.id)"
  }
  $seenDatasetIds[$dataset.id] = $true
  if ($dataset.status -ne 'ELIGIBLE') {
    throw "Only ELIGIBLE entries may appear in manifest.datasets: $($dataset.id)"
  }
  if ($dataset.recipe_role -notin @('BASE_SCRIPT_ADAPTATION', 'LEXICON')) {
    throw "Unsupported recipe role for $($dataset.id): $($dataset.recipe_role)"
  }
  if ([string]::IsNullOrWhiteSpace($dataset.license.name) -or
      [string]::IsNullOrWhiteSpace($dataset.license.url) -or
      [string]::IsNullOrWhiteSpace($dataset.license.retrieved_at)) {
    throw "Incomplete license receipt metadata for $($dataset.id)"
  }
  Assert-EligibleUrl -Url $dataset.license.url
  if ([string]::IsNullOrWhiteSpace($dataset.source.revision)) {
    throw "Missing immutable source revision for $($dataset.id)"
  }
  $artifacts = @($dataset.artifacts)
  if ($artifacts.Count -eq 0) {
    throw "Dataset has no artifacts: $($dataset.id)"
  }
  $seenFilenames = @{}
  foreach ($artifact in $artifacts) {
    Assert-LeafFilename -Filename $artifact.filename
    if ($seenFilenames.ContainsKey($artifact.filename)) {
      throw "Duplicate artifact filename in $($dataset.id): $($artifact.filename)"
    }
    $seenFilenames[$artifact.filename] = $true
    Assert-EligibleUrl -Url $artifact.url
    if ([int64]$artifact.expected_size_bytes -le 0) {
      throw "Artifact requires a positive expected_size_bytes: $($artifact.filename)"
    }
    if ($null -eq $artifact.expected_sha256) {
      if ($artifact.verification -ne 'SIZE_THEN_RECORD_SHA256') {
        throw "Unpinned artifact must record its observed SHA-256: $($artifact.filename)"
      }
    } elseif ($artifact.expected_sha256 -notmatch $Sha256Pattern -or
              $artifact.verification -ne 'SHA256_AND_SIZE') {
      throw "Invalid SHA-256 verification pin for $($artifact.filename)"
    }
  }
}

if ($DatasetId) {
  foreach ($requestedId in $DatasetId) {
    if (-not $seenDatasetIds.ContainsKey($requestedId)) {
      throw "Unknown or excluded dataset id: $requestedId"
    }
  }
  $selectedDatasets = @($datasets | Where-Object { $_.id -in $DatasetId })
} else {
  $selectedDatasets = $datasets
}

if ($ListOnly) {
  $selectedDatasets |
    Select-Object id, title, recipe_role, @{Name='license'; Expression={$_.license.name}},
      @{Name='artifact_count'; Expression={@($_.artifacts).Count}} |
    Format-Table -AutoSize
  return
}
if (-not $AcceptLicenses) {
  throw 'Review the manifest and pass -AcceptLicenses to perform owner-controlled downloads.'
}
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
  throw 'curl.exe is required for fail-closed HTTPS downloads.'
}

if ([string]::IsNullOrWhiteSpace($DestinationRoot)) {
  $DestinationRoot = [string]$manifest.destination_root
}
if (-not [System.IO.Path]::IsPathRooted($DestinationRoot) -or
    $DestinationRoot.StartsWith('\\') -or
    $DestinationRoot.StartsWith('//')) {
  throw "Destination root must be one absolute local path: $DestinationRoot"
}
$fullDestinationRoot = [System.IO.Path]::GetFullPath($DestinationRoot)
$volumeRoot = [System.IO.Path]::GetPathRoot($fullDestinationRoot)
$trimCharacters = [char[]]@('\', '/')
if ($fullDestinationRoot.TrimEnd($trimCharacters) -eq $volumeRoot.TrimEnd($trimCharacters)) {
  throw 'Destination root must not be a filesystem volume root.'
}

foreach ($dataset in $selectedDatasets) {
  $datasetDirectory = Join-Path $fullDestinationRoot $dataset.id
  New-Item -ItemType Directory -Force -Path $datasetDirectory | Out-Null
  $downloadReceiptPath = Join-Path $datasetDirectory 'DOWNLOAD_RECEIPT.json'
  $priorReceipt = $null
  if (Test-Path -LiteralPath $downloadReceiptPath -PathType Leaf) {
    try {
      $priorReceipt = Get-Content -Raw -LiteralPath $downloadReceiptPath | ConvertFrom-Json
    } catch {
      throw "Existing download receipt is unreadable; data was left untouched: $downloadReceiptPath"
    }
  }

  $receiptArtifacts = @()
  foreach ($artifact in @($dataset.artifacts)) {
    $destination = Join-Path $datasetDirectory $artifact.filename
    $partial = "$destination.partial"
    $expectedBytes = [int64]$artifact.expected_size_bytes
    $expectedHash = if ($null -eq $artifact.expected_sha256) {
      $null
    } else {
      [string]$artifact.expected_sha256
    }

    if (Test-Path -LiteralPath $destination -PathType Leaf) {
      $observedBytes = (Get-Item -LiteralPath $destination).Length
      if ($observedBytes -ne $expectedBytes) {
        throw "Existing artifact size mismatch and was left untouched: $destination"
      }
      $observedHash = Get-LowerSha256 -Path $destination
      if ($null -ne $expectedHash) {
        if ($observedHash -ne $expectedHash) {
          throw "Existing artifact SHA-256 mismatch and was left untouched: $destination"
        }
      } else {
        if ($null -eq $priorReceipt) {
          throw "Existing size-only artifact has no recorded SHA-256 receipt: $destination"
        }
        $priorArtifact = @($priorReceipt.artifacts) |
          Where-Object { $_.filename -eq $artifact.filename } |
          Select-Object -First 1
        if ($null -eq $priorArtifact -or
            $priorArtifact.observed_sha256 -notmatch $Sha256Pattern -or
            $priorArtifact.observed_sha256 -ne $observedHash) {
          throw "Existing size-only artifact has no matching recorded SHA-256 receipt: $destination"
        }
      }
      Write-Host "VERIFIED existing $($dataset.id)/$($artifact.filename)" -ForegroundColor Green
    } else {
      Write-Host "Downloading owner-approved artifact: $($dataset.id)/$($artifact.filename)"
      $curlArguments = @(
        '--fail',
        '--location',
        '--retry', '3',
        '--retry-all-errors',
        '--retry-delay', '10',
        '--proto', '=https',
        '--proto-redir', '=https',
        '--continue-at', '-',
        '--output', $partial,
        [string]$artifact.url
      )
      & curl.exe @curlArguments
      if ($LASTEXITCODE -ne 0) {
        throw "curl failed with exit code $LASTEXITCODE; partial retained: $partial"
      }
      if (-not (Test-Path -LiteralPath $partial -PathType Leaf)) {
        throw "curl reported success but no partial file exists: $partial"
      }
      $observedBytes = (Get-Item -LiteralPath $partial).Length
      if ($observedBytes -ne $expectedBytes) {
        throw "Downloaded artifact size mismatch; partial retained: $partial"
      }
      $observedHash = Get-LowerSha256 -Path $partial
      if ($null -ne $expectedHash -and $observedHash -ne $expectedHash) {
        throw "Downloaded artifact SHA-256 mismatch; partial retained: $partial"
      }
      Move-Item -LiteralPath $partial -Destination $destination
      Write-Host "VERIFIED $($dataset.id)/$($artifact.filename)" -ForegroundColor Green
    }

    $receiptArtifacts += [ordered]@{
      filename = [string]$artifact.filename
      source_url = [string]$artifact.url
      expected_size_bytes = $expectedBytes
      observed_size_bytes = $observedBytes
      expected_sha256 = $expectedHash
      observed_sha256 = $observedHash
      verification = [string]$artifact.verification
    }
  }

  $downloadReceipt = [ordered]@{
    schema_version = '1.0.0'
    dataset_id = [string]$dataset.id
    source_revision = [string]$dataset.source.revision
    verified_at_utc = [DateTime]::UtcNow.ToString('o')
    artifacts = $receiptArtifacts
  }
  Write-AtomicJson -Path $downloadReceiptPath -Payload $downloadReceipt

  $licenseReceipt = [ordered]@{
    schema_version = '1.0.0'
    dataset_id = [string]$dataset.id
    dataset_title = [string]$dataset.title
    recipe_role = [string]$dataset.recipe_role
    license_name = [string]$dataset.license.name
    license_url = [string]$dataset.license.url
    license_retrieved_at = [string]$dataset.license.retrieved_at
    source_repository = [string]$dataset.source.repository_url
    source_revision = [string]$dataset.source.revision
    terms_review_required_each_run = $true
  }
  Write-AtomicJson -Path (Join-Path $datasetDirectory 'LICENSE_RECEIPT.json') -Payload $licenseReceipt
}

Write-Host 'All selected open-dataset artifacts verified; archives remain unexpanded.' -ForegroundColor Green

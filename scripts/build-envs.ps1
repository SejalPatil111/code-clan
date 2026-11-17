param([string[]]$Only = @())
# Build pre-built CodeClan execution environment images (run from the repository root).
#   .\scripts\build-envs.ps1                   # all environments
#   .\scripts\build-envs.ps1 -Only ml,cv       # selected ones
$ErrorActionPreference = "Stop"
$envs = @(
  @{id="datascience"; tag="1.0"},
  @{id="ml";          tag="1.0"},
  @{id="scientific";  tag="1.0"},
  @{id="cv";          tag="1.0"},
  @{id="nlp";         tag="1.0"},
  @{id="dl-torch";    tag="1.0"; extra="https://download.pytorch.org/whl/cpu"},
  @{id="dl-tf";       tag="1.0"}
)
docker build -t codeclan-sandbox:latest backend/sandbox
foreach ($e in $envs) {
  if ($Only.Count -gt 0 -and ($Only -notcontains $e.id)) { continue }
  Write-Host "=== Building codeclan-env-$($e.id):$($e.tag) ==="
  $args = @("build","-f","backend/sandbox/Dockerfile.pyenv","--build-arg","ENV_ID=$($e.id)","-t","codeclan-env-$($e.id):$($e.tag)")
  if ($e.extra) { $args += @("--build-arg","PIP_EXTRA_INDEX=$($e.extra)") }
  $args += "backend/sandbox"
  & docker @args
  if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $($e.id)"; exit 1 }
}
docker images --format "{{.Repository}}:{{.Tag}}  {{.Size}}" | Select-String "codeclan-(env|sandbox)"

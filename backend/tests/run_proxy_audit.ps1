param(
  [ValidateSet("tecnativa","policy")] [string]$Proxy = "tecnativa",
  [string]$LegitRuntime = "runc"
)
# Runs backend/tests/docker_api_abuse_probe.sh against the selected Docker socket proxy.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$net = "audit_net"; $px = "audit-proxy"; $victim = "audit-victim"
docker rm -f $px $victim 2>&1 | Out-Null
docker network rm $net 2>&1 | Out-Null
docker network create $net | Out-Null
docker run -d --name $victim alpine:3 sleep 600 | Out-Null

if ($Proxy -eq "tecnativa") {
  docker run -d --name $px --network $net `
    -e INFO=1 -e PING=1 -e VERSION=1 -e CONTAINERS=1 -e IMAGES=1 -e POST=1 `
    -e AUTH=0 -e BUILD=0 -e COMMIT=0 -e CONFIGS=0 -e DISTRIBUTION=0 -e EXEC=0 -e NETWORKS=0 `
    -e SECRETS=0 -e SERVICES=0 -e SWARM=0 -e SYSTEM=0 -e VOLUMES=0 `
    -v /var/run/docker.sock:/var/run/docker.sock:ro tecnativa/docker-socket-proxy:latest | Out-Null
} else {
  docker run -d --name $px --network $net `
    -e PROXY_ALLOWED_RUNTIMES=$LegitRuntime -e PROXY_ALLOWED_IMAGES="codeclan-sandbox:latest,codeclan-env-*" `
    -v /var/run/docker.sock:/var/run/docker.sock:ro codeclan-policy-proxy:latest | Out-Null
}
Start-Sleep -Seconds 4
$probe = Join-Path $root "backend\tests\docker_api_abuse_probe.sh"
$out = docker run --rm --network $net -e DOCKER_HOST=tcp://${px}:2375 -e LEGIT_RUNTIME=$LegitRuntime -e VICTIM=$victim `
  -v "${probe}:/probe.sh:ro" docker:27-cli sh /probe.sh 2>&1
$out | Where-Object { $_ -like "PROBE|*" }
"--- host-side ground truth (containers that exist after probe) ---"
if ($env:SHOW_PROXY_LOG -eq "1") { docker logs $px 2>&1 | Select-String "LEGIT|codeclan-sbx-legit|containers/create" | Select-Object -Last 6 }
docker ps -a --format "{{.Names}}" | Where-Object { $_ -like "codeclan-sbx-*" -or $_ -eq "not-a-sandbox" }
"victim still running? -> " + (docker ps --filter "name=$victim" --format "{{.Names}}")
docker rm -f $px $victim 2>&1 | Out-Null
docker ps -a --format "{{.Names}}" | Where-Object { $_ -like "codeclan-sbx-*" -or $_ -eq "not-a-sandbox" } | ForEach-Object { docker rm -f $_ | Out-Null }
docker network rm $net 2>&1 | Out-Null

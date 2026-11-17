#!/usr/bin/env bash
# Build pre-built CodeClan execution environment images (run from the repository root).
#   scripts/build-envs.sh            # all
#   scripts/build-envs.sh ml cv      # selected
set -euo pipefail
ONLY=("$@")
declare -A EXTRA=( ["dl-torch"]="https://download.pytorch.org/whl/cpu" )
ENVS=(datascience ml scientific cv nlp dl-torch dl-tf)
docker build -t codeclan-sandbox:latest backend/sandbox
for id in "${ENVS[@]}"; do
  if [ ${#ONLY[@]} -gt 0 ] && [[ ! " ${ONLY[*]} " =~ " ${id} " ]]; then continue; fi
  echo "=== Building codeclan-env-${id}:1.0 ==="
  args=(build -f backend/sandbox/Dockerfile.pyenv --build-arg "ENV_ID=${id}" -t "codeclan-env-${id}:1.0")
  [ -n "${EXTRA[$id]:-}" ] && args+=(--build-arg "PIP_EXTRA_INDEX=${EXTRA[$id]}")
  docker "${args[@]}" backend/sandbox
done
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep -E 'codeclan-(env|sandbox)'

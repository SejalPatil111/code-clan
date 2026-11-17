#!/bin/sh
# Docker API abuse probe. Runs INSIDE a docker:cli container whose DOCKER_HOST points at the
# proxy under test. It simulates a COMPROMISED grader and prints ALLOWED/BLOCKED per attack.
# Env: IMAGE (approved sandbox image), VICTIM (an unrelated running container name),
#      LEGIT_RUNTIME (runtime used by the legitimate sandbox probe, e.g. runc or runsc).
IMAGE="${IMAGE:-codeclan-sandbox:latest}"
VICTIM="${VICTIM:-audit-victim}"
LEGIT_RUNTIME="${LEGIT_RUNTIME:-runc}"
N=0

try() {  # try <label> <command...>  -> prints ALLOWED if command exit 0
  label="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "PROBE|$label|ALLOWED"; else echo "PROBE|$label|BLOCKED"; fi
}

cleanup_name() { docker rm -f "$1" >/dev/null 2>&1; }

for n in x1 x2 x3 x4 x5 x6 x7 x8; do cleanup_name codeclan-sbx-$n; done

try "create_privileged_container" docker create --name codeclan-sbx-x1 --privileged "$IMAGE" /bin/true
try "create_host_bind_mount" docker create --name codeclan-sbx-x2 -v /:/hostroot "$IMAGE" /bin/true
try "create_host_network_and_pid_ns" docker create --name codeclan-sbx-x3 --network host --pid host "$IMAGE" /bin/true
try "create_with_cap_add_all" docker create --name codeclan-sbx-x4 --cap-add ALL "$IMAGE" /bin/true
try "create_with_host_device" docker create --name codeclan-sbx-x5 --device /dev/kmsg "$IMAGE" /bin/true
try "create_with_seccomp_unconfined" docker create --name codeclan-sbx-x6 --security-opt seccomp=unconfined "$IMAGE" /bin/true
try "create_with_networking_enabled" docker create --name codeclan-sbx-x7 --network bridge --cap-drop ALL --security-opt no-new-privileges --read-only --user 65534:65534 --runtime "$LEGIT_RUNTIME" --memory 256m --pids-limit 64 "$IMAGE" /bin/true
try "create_unapproved_image" docker create --name codeclan-sbx-x8 alpine:3 /bin/true
try "create_unapproved_name_prefix" docker create --name not-a-sandbox --network none --cap-drop ALL --security-opt no-new-privileges --read-only --user 65534:65534 --runtime "$LEGIT_RUNTIME" --memory 256m --pids-limit 64 --ipc none "$IMAGE" /usr/local/bin/sandbox-runner compile
try "create_runtime_override_runc" docker create --name codeclan-sbx-rt --network none --ipc none --cap-drop ALL --security-opt no-new-privileges --read-only --user 65534:65534 --runtime runc --memory 256m --pids-limit 64 "$IMAGE" /usr/local/bin/sandbox-runner compile
try "create_oversized_memory" docker create --name codeclan-sbx-mem --network none --ipc none --cap-drop ALL --security-opt no-new-privileges --read-only --user 65534:65534 --runtime "$LEGIT_RUNTIME" --memory 64g --pids-limit 64 "$IMAGE" /usr/local/bin/sandbox-runner compile
try "create_arbitrary_command" docker create --name codeclan-sbx-cmd --network none --ipc none --cap-drop ALL --security-opt no-new-privileges --read-only --user 65534:65534 --runtime "$LEGIT_RUNTIME" --memory 256m --pids-limit 64 "$IMAGE" /bin/sh -c id
try "exec_into_unrelated_container" docker exec "$VICTIM" id
try "inspect_unrelated_container_env" docker inspect "$VICTIM"
try "read_unrelated_container_logs" docker logs "$VICTIM"
try "kill_unrelated_container" docker kill "$VICTIM"
try "stop_unrelated_container" docker stop -t 1 "$VICTIM"
try "remove_unrelated_container" docker rm -f "$VICTIM"
try "list_all_containers_unfiltered" docker ps -a
try "network_create" docker network create probe-net
try "network_list" docker network ls
try "volume_create" docker volume create probe-vol
try "volume_list" docker volume ls
try "build_image" sh -c 'printf "FROM scratch\nCOPY . /\n" | docker build -t probe-build -'
try "pull_image" docker pull alpine:3.19
try "docker_info_host_details" docker info
try "docker_system_df" docker system df
# Legitimate sandbox create must still work (functional check of the policy)
try "LEGIT_sandbox_create" docker create --name codeclan-sbx-legit --network none --ipc none --cap-drop ALL --security-opt no-new-privileges --read-only --user 65534:65534 --runtime "$LEGIT_RUNTIME" --memory 256m --memory-swap 256m --cpus 0.5 --pids-limit 64 --tmpfs /work:rw,exec,nosuid,nodev,size=32m,mode=1777 --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777 -i "$IMAGE" /usr/local/bin/sandbox-runner compile
try "LEGIT_sandbox_inspect" docker inspect codeclan-sbx-legit
try "LEGIT_sandbox_remove" docker rm -f codeclan-sbx-legit

# Report what actually got created (needs a direct view; use the proxy's own listing if allowed)
for n in x1 x2 x3 x4 x5 x6 x7 x8 rt mem cmd legit; do cleanup_name codeclan-sbx-$n; done
cleanup_name not-a-sandbox; docker network rm probe-net >/dev/null 2>&1; docker volume rm probe-vol >/dev/null 2>&1
echo "PROBE|DONE|DONE"

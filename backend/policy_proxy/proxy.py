"""
CodeClan Docker policy proxy.

Listens on TCP :2375 (internal network only) and forwards ONLY policy-approved Docker Engine API
requests to the real Docker socket. Request bodies are fully read and validated by `policy.Policy`
before a single byte is forwarded. Anything else gets `403`.

Security properties / limits (also see docs):
  * Requests with Transfer-Encoding, duplicate Content-Length, or bodies > 1 MiB are rejected
    (prevents request smuggling past the validator).
  * After an approved `attach` (HTTP upgrade) the connection becomes a raw relay for that connection only.
  * This proxy is itself a privileged component (it can reach the Docker socket). It is small, stdlib-only,
    runs read-only with all capabilities dropped, and is reachable only from the grader on an internal network.
"""

import os
import re
import socket
import socketserver
import sys
import threading
import time

from policy import Policy

_ID_JSON_RE = re.compile(rb'"Id"\s*:\s*"([0-9a-fA-F]{64})"')

LISTEN_PORT = int(os.environ.get("PROXY_PORT", "2375"))
UPSTREAM = os.environ.get("DOCKER_UPSTREAM_SOCKET", "/var/run/docker.sock")
MAX_HEADER = 64 * 1024
MAX_BODY = 1024 * 1024
POLICY = Policy()


def log(msg: str) -> None:
    sys.stdout.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
    sys.stdout.flush()


def deny_response(reason: str, code: int = 403) -> bytes:
    body = ('{"message":"CodeClan docker policy: ' + reason.replace('"', "'") + '"}').encode()
    status = {403: "Forbidden", 400: "Bad Request", 413: "Payload Too Large"}.get(code, "Forbidden")
    return (
        f"HTTP/1.1 {code} {status}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
        "Connection: keep-alive\r\n\r\n"
    ).encode() + body


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        client: socket.socket = self.request
        peer = self.client_address[0]
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            upstream.connect(UPSTREAM)
        except Exception as exc:
            log(f"[{peer}] upstream connect failed: {exc}")
            return
        lock = threading.Lock()

        def pump_up_to_client() -> None:
            try:
                while True:
                    data = upstream.recv(65536)
                    if not data:
                        break
                    for m_id in _ID_JSON_RE.finditer(data):
                        POLICY.register_owned_id(m_id.group(1).decode("ascii"))
                    with lock:
                        client.sendall(data)
            except Exception:
                pass
            finally:
                for s in (client, upstream):
                    try:
                        s.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass

        t = threading.Thread(target=pump_up_to_client, daemon=True)
        t.start()

        buf = b""
        try:
            while True:
                while b"\r\n\r\n" not in buf:
                    if len(buf) > MAX_HEADER:
                        with lock:
                            client.sendall(deny_response("header too large", 400))
                        return
                    chunk = client.recv(65536)
                    if not chunk:
                        return
                    buf += chunk
                head, _, rest = buf.partition(b"\r\n\r\n")
                lines = head.decode("latin-1").split("\r\n")
                try:
                    method, target, version = lines[0].split(" ")
                except ValueError:
                    with lock:
                        client.sendall(deny_response("malformed request line", 400))
                    return
                headers: dict = {}
                dup_cl = False
                for ln in lines[1:]:
                    if ":" not in ln:
                        continue
                    k, v = ln.split(":", 1)
                    k = k.strip().lower()
                    if k == "content-length" and k in headers:
                        dup_cl = True
                    headers[k] = v.strip()
                if "transfer-encoding" in headers or dup_cl:
                    with lock:
                        client.sendall(deny_response("Transfer-Encoding/duplicate Content-Length not allowed", 400))
                    return
                try:
                    clen = int(headers.get("content-length", "0") or "0")
                except ValueError:
                    return
                if clen < 0 or clen > MAX_BODY:
                    with lock:
                        client.sendall(deny_response("body too large", 413))
                    return
                while len(rest) < clen:
                    chunk = client.recv(65536)
                    if not chunk:
                        return
                    rest += chunk
                body, buf = rest[:clen], rest[clen:]

                ok, reason = POLICY.check_request(method, target, body)
                log(f"[{peer}] {'ALLOW' if ok else 'DENY '} {method} {target.split('?')[0]} -> {reason}")
                if not ok:
                    with lock:
                        client.sendall(deny_response(reason))
                    continue
                upstream.sendall(head + b"\r\n\r\n" + body)
                if headers.get("upgrade") or "upgrade" in headers.get("connection", "").lower():
                    # Approved hijacked stream (container attach): raw relay for this connection only
                    if buf:
                        upstream.sendall(buf)
                        buf = b""
                    while True:
                        data = client.recv(65536)
                        if not data:
                            try:
                                upstream.shutdown(socket.SHUT_WR)
                            except Exception:
                                pass
                            t.join(timeout=600)
                            return
                        upstream.sendall(data)
        except Exception as exc:
            log(f"[{peer}] connection error: {exc}")
        finally:
            for s in (client, upstream):
                try:
                    s.close()
                except Exception:
                    pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    log(
        f"CodeClan policy proxy listening on :{LISTEN_PORT} -> {UPSTREAM}; "
        f"runtimes={sorted(POLICY.allowed_runtimes)} images={POLICY.allowed_images}"
    )
    with Server(("0.0.0.0", LISTEN_PORT), Handler) as srv:
        srv.serve_forever()

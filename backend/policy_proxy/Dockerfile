# CodeClan Docker policy proxy (body-validating Docker API filter). Stdlib only.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY policy.py proxy.py ./
# Needs read access to the docker socket (owned by root:docker on hosts). Run as root inside the
# container but with ALL capabilities dropped, read-only rootfs and no-new-privileges (see compose).
CMD ["python", "proxy.py"]

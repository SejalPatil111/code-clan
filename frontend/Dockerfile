# CodeClan frontend: React + Vite development server
# Vite 8 requires Node.js 20.19+ / 22.12+. Debian-based (glibc) image is used so the
# native Rolldown / LightningCSS binaries from package-lock.json install cleanly.
FROM node:22-bookworm-slim

ENV NODE_ENV=development

WORKDIR /app

# Install dependencies from the existing lockfile (cached layer).
COPY --chown=node:node package.json package-lock.json ./
RUN chown node:node /app
USER node
RUN npm ci --no-audit --no-fund

COPY --chown=node:node . .

EXPOSE 5173

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD node -e "fetch('http://127.0.0.1:5173/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

# --host 0.0.0.0 makes the dev server reachable from outside the container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]

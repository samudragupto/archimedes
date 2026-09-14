# ARCHIMEDES web container (docker compose `web` service).
# Production deploys go to Vercel (see docs/DEPLOYMENT.md); this image exists
# so the whole stack runs with one `docker compose up` on a laptop.
FROM node:20-alpine

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

WORKDIR /app

# Dependency layer (cached until the lockfile changes)
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --no-frozen-lockfile

COPY . .

EXPOSE 3000
# compose overrides this with `pnpm dev` for hot reload
CMD ["pnpm", "dev"]

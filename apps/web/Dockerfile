# ARCHIMEDES web container (docker compose `web` service).
# Production deploys go to Vercel (see docs/DEPLOYMENT.md); this image exists
# so the whole stack runs with one `docker compose up` on a laptop — and so a
# standalone `docker run` serves the production build.
#
# NOTE: NEXT_PUBLIC_* vars are inlined into the client bundle at BUILD time.
# Override them with --build-arg when building for a real deployment; the
# compose dev path ignores this baked build entirely (it hot-reloads with the
# runtime env from .env instead).
FROM node:20-alpine

WORKDIR /app

# Dependency layer (cached until the lockfile changes)
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

ARG NEXT_PUBLIC_SUPABASE_URL=https://placeholder.supabase.co
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY=placeholder-anon-key
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

EXPOSE 3000
# compose overrides this with `npm run dev` for hot reload
CMD ["npm", "run", "start"]

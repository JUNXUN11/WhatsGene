# WhatsGene frontend — Nuxt 3 SSR. Listens on 3000 inside the compose
# network; Caddy is the only public entry point.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Public API base is baked as the build default and can still be overridden
# at container start with NUXT_PUBLIC_API_BASE (Nuxt runtime config).
ARG NUXT_PUBLIC_API_BASE=http://localhost:8000
ENV NUXT_PUBLIC_API_BASE=$NUXT_PUBLIC_API_BASE
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV HOST=0.0.0.0 \
    PORT=3000 \
    NODE_ENV=production
COPY --from=build /app/.output ./.output
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]

# Imagem de produção — build standalone do Next.js (ver output: "standalone"
# em next.config.ts), sem node_modules completo na imagem final.
#
# `deps` é o estágio reaproveitado pelo docker-compose.yml de dev (build
# com `target: deps`) — node_modules instalado, código montado por bind
# mount, roda com `next dev` (hot reload).

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]


FROM deps AS builder
RUN npm run build


FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]

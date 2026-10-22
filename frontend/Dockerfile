# Build context : ce dossier (frontend/).
#   docker build -f frontend/Dockerfile -t traversal-frontend frontend
FROM node:22-slim AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Aucune URL d'API n'est bakée : le relais serveur (app/api/[...path]/route.ts) lit
# API_URL et API_KEY au RUNTIME.
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# Fichiers statiques (drapeaux des pays) : non inclus dans la sortie standalone.
COPY --from=builder /app/public ./public

EXPOSE 3000
# Scaleway injects $PORT.
CMD ["sh", "-c", "PORT=${PORT:-3000} HOSTNAME=0.0.0.0 node server.js"]

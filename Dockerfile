FROM node:22-bookworm-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY server ./server
COPY public ./public
COPY .env.example ./

ENV NODE_ENV=production
ENV PORT=3000
ENV DB_PATH=/app/data/data.sqlite

RUN mkdir -p /app/data
EXPOSE 3000

CMD ["npm", "start"]

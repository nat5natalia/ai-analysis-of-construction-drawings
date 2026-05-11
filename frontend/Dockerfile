# сборка
FROM node:20-alpine AS builder

WORKDIR /app

# Копируем файлы с зависимостями
COPY package*.json ./
RUN npm ci

# Копируем исходный код
COPY . .

# Сборка проекта (tsc -b && vite build из скрипта build)
RUN npm run build

# сервер 
FROM nginx:alpine

# Копируем собранные файлы из папки dist
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

# Yandex Spotify Connect

Автономный мост между Spotify Connect и Яндекс Станциями с мультирумом и веб-интерфейсом.

## 🚀 Быстрый запуск (1 команда)

Создайте `docker-compose.yml`:

```yaml
services:
  yandex-spotify-connect:
    image: ghcr.io/badkiko/yandex-spotify-connect:latest
    container_name: yandex_spotify_connect
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./cache:/app/cache
      - ./config.yaml:/app/config.yaml
```

Запустите:

```bash
docker compose up -d
```

Откройте в браузере: **`http://<IP_СЕРВЕРА>:8555`** и отсканируйте QR-код для авторизации за 1 клик.

## 📱 Как пользоваться

1. Откройте приложение **Spotify** на телефоне или ПК.
2. В списке устройств выберите нужную Яндекс Станцию (например, **«Яндекс Станция 2 (Spotify)»**).
3. Включите трек.

# Despliegue en Docker (Ubuntu / AWS)

## Prerrequisitos
- Servidor Ubuntu con acceso SSH (p. ej. EC2) y Docker + Docker Compose instalados:
  ```bash
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  ```
- Abrir el puerto `8000/tcp` en el **Security Group** de la instancia para la IP 51.44.18.248 (o el puerto externo que quieras usar).
- Opcional: crear el directorio `/opt/smart-fenix` para alojar el proyecto y los datos persistentes.

## Copiar el proyecto
1. Clonar o copiar el código al servidor:
   ```bash
   git clone <tu-repo> smart-fenix
   cd smart-fenix
   ```
2. Crea un archivo `.env` (opcional) para variables sensibles:
   ```bash
   cat <<'EOF' > .env
   SECRET_KEY=superclave
   DEFAULT_USERNAME=admin
   DEFAULT_PASSWORD=123
   ROBOFLOW_API_KEY=
   ROBOFLOW_WORKSPACE=
   ROBOFLOW_WORKFLOW=
   EOF
   ```

## Construir y ejecutar
```bash
docker compose build
docker compose up -d
```

La aplicación quedará publicada en `http://51.44.18.248:8000`. Cambia la IP o el puerto según tu configuración.

## Volúmenes de datos
- Los archivos y la base de datos SQLite se guardan en el directorio `./data` del host (montado dentro del contenedor en `/data`).
- Para hacer una copia de seguridad:
  ```bash
  tar czf backup-smart-fenix.tgz data
  ```

## Logs y mantenimiento
- Ver logs: `docker compose logs -f`
- Reiniciar servicio: `docker compose restart`
- Actualizar imagen tras cambios en el código:
  ```bash
  git pull
  docker compose build
  docker compose up -d
  ```

## Detener y eliminar
```bash
docker compose down
```

Esto detiene el contenedor pero mantiene el volumen `./data`. Elimina el directorio manualmente si quieres borrar la base de datos y los archivos subidos.

# Usa una imagen base oficial de Python. Se recomienda usar versiones "slim" por ser más ligeras.
FROM python:3.11-slim

# Establece el directorio de trabajo dentro del contenedor en /app
WORKDIR /app

# Copia primero el archivo de requerimientos.
# Esto aprovecha el caché de Docker: si no cambias las dependencias, no se volverán a instalar.
COPY requirements.txt /app/requirements.txt

# Instala las dependencias del proyecto
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copia todo el contenido de tu carpeta 'backend' al directorio de trabajo /app del contenedor
COPY . /app

# Expone el puerto 8080 para que el contenedor pueda recibir tráfico
EXPOSE 8080

# El comando para iniciar la aplicación cuando el contenedor se ejecute.
# Usamos 0.0.0.0 para que sea accesible desde fuera del contenedor.
# Cloud Run espera por defecto el puerto 8080.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
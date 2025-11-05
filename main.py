# main.py

import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import datetime
from dotenv import load_dotenv

# 1. CARGAR CONFIGURACIÓN
load_dotenv()

# 2. CONEXIÓN SEGURA CON GOOGLE SHEETS
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

# Esta es la ruta correcta para Docker en Render
SECRET_FILE_PATH = "credentials.json"
# Para pruebas locales, descomenta la siguiente línea y asegúrate de que el archivo está en la misma carpeta
# SECRET_FILE_PATH = "credentials.json" 

try:
    creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET_FILE_PATH, scope)
    client = gspread.authorize(creds)
except FileNotFoundError:
    raise RuntimeError(f"Error Crítico: No se encontró el archivo de credenciales en la ruta '{SECRET_FILE_PATH}'.")
except Exception as e:
    raise RuntimeError(f"Error al cargar las credenciales desde '{SECRET_FILE_PATH}'. Error: {e}")

# Abre la hoja de cálculo por su ID
sheet_id = os.getenv("GOOGLE_SHEET_ID")
if not sheet_id:
    raise ValueError("Error Crítico: La variable de entorno GOOGLE_SHEET_ID no está configurada.")

try:
    sheet = client.open_by_key(sheet_id).sheet1
except Exception as e:
    raise RuntimeError(f"Ocurrió un error al abrir Google Sheet. Error: {e}")

# 3. LÓGICA DE LA API CON FASTAPI
app = FastAPI(
    title="API Validador de Entradas",
    version="3.0.1"
)
class Ticket(BaseModel):
    f1_code: int

@app.post("/validate-ticket", tags=["Validación"])
def validate_ticket(ticket: Ticket):
    try:
        cell = sheet.find(str(ticket.f1_code), in_column=10)
        
        # --- INICIO DE LA CORRECCIÓN ---
        # Añadimos esta verificación crucial.
        # Si 'cell' es None, significa que el código no se encontró.
        if not cell:
            # Lanzamos una excepción controlada que FastAPI convierte en un error 404.
            raise HTTPException(status_code=404, detail="ENTRADA INVÁLIDA: El código no existe en la base de datos.")
        # --- FIN DE LA CORRECCIÓN ---

    except Exception as e:
        # Este bloque captura cualquier otro error durante la comunicación
        if isinstance(e, HTTPException):
            raise e # Re-lanza la excepción que ya creamos
        raise HTTPException(status_code=503, detail=f"Error de comunicación con Google Sheets: {e}")

    # Si el código llega aquí, 'cell' es un objeto válido y podemos continuar.
    row_data = sheet.row_values(cell.row)

    COL_NOMBRE = 2
    COL_VALIDADO = 24

    estado_validacion = row_data[COL_VALIDADO - 1] if len(row_data) >= COL_VALIDADO else ""
    nombre_asistente = row_data[COL_NOMBRE - 1] if len(row_data) >= COL_NOMBRE else "Asistente no encontrado"

    if estado_validacion:
        raise HTTPException(
            status_code=409,
            detail=f"ENTRADA RECHAZADA: Este código ya fue utilizado."
        )

    try:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sheet.update_cell(cell.row, COL_VALIDADO, '1')
        return {
            "status": "success",
            "message": "ACCESO AUTORIZADO",
            "data": {
                "nombre": nombre_asistente,
                "hora_validacion": timestamp
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error Crítico: No se pudo actualizar el estado de la entrada. Por favor, inténtelo de nuevo. Error: {e}")
# main.py

import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fastapi import FastAPI, HTTPException, responses
from pydantic import BaseModel
import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from fastapi.middleware.cors import CORSMiddleware

# 1. CARGAR CONFIGURACIÓN
load_dotenv()

# 2. CONEXIÓN SEGURA CON GOOGLE SHEETS
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

# Esta es la ruta para Docker en Render
SECRET_FILE_PATH = "credentials.json"
# Para pruebas locales, crea un .env y añade: SECRET_FILE_PATH_LOCAL="credentials.json"
if os.getenv("SECRET_FILE_PATH_LOCAL"):
    SECRET_FILE_PATH = os.getenv("SECRET_FILE_PATH_LOCAL")

try:
    creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET_FILE_PATH, scope)
    client = gspread.authorize(creds)
except FileNotFoundError:
    raise RuntimeError(f"Error Crítico: No se encontró el archivo de credenciales en '{SECRET_FILE_PATH}'.")
except Exception as e:
    raise RuntimeError(f"Error al cargar las credenciales. Error: {e}")

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
    description="API para validar entradas de un evento.",
    version="4.1.0"
)

origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",
    "https://validador-qr-frontend.vercel.app"

]


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todos los orígenes
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"],  # Permite todos los encabezados
)


class Ticket(BaseModel):
    f1_code: str

@app.post("/validate-ticket", tags=["Validación"])
def validate_ticket(ticket: Ticket):
    try:
        # <<< CAMBIO: Buscando en la columna J (10) según tu indicación >>>
        cell = sheet.find(str(ticket.f1_code), in_column=10)
    except Exception as e:
        error_response = {
            "status": "error", "error_code": "SERVICE_UNAVAILABLE",
            "message": f"Error de comunicación con Google Sheets: {e}"
        }
        return responses.JSONResponse(status_code=503, content=error_response)

    # --- Escenario 3: Entrada NO EXISTE ---
    if not cell:
        error_response = {
            "status": "error",
            "error_code": "NOT_FOUND",
            "message": "Código QR no válido. La entrada no existe."
        }
        raise HTTPException(status_code=404, detail=error_response)

    row_data = sheet.row_values(cell.row)

    # <<< CAMBIO: Añadida la columna del ID de usuario >>>
    # Definimos las columnas según tu indicación:
    COL_USER_ID = 1   # Columna A
    COL_NOMBRE = 2    # Columna B
    COL_VALIDADO = 21 # Columna X

    # Extraemos los datos de forma segura
    user_id = row_data[COL_USER_ID - 1] if len(row_data) >= COL_USER_ID else "N/A"
    nombre_asistente = row_data[COL_NOMBRE - 1] if len(row_data) >= COL_NOMBRE else "N/A"
    estado_validacion = row_data[COL_VALIDADO - 1] if len(row_data) >= COL_VALIDADO else ""

    # --- Escenario 2: Entrada YA REGISTRADA ---
    if estado_validacion:
        # <<< CAMBIO: Añadido el user_id a la respuesta de error >>>
        error_response = {
            "status": "error",
            "error_code": "ALREADY_SCANNED",
            "message": "Esta entrada ya fue registrada.",
            "ticket_data": {
                "user_name": nombre_asistente,
                "user_id": user_id,
                "scanned_at": estado_validacion
            }
        }
        raise HTTPException(status_code=409, detail=error_response)

    # --- Escenario 1: ÉXITO (Entrada Válida) ---
    try:
        timestamp = datetime.datetime.now(ZoneInfo("America/La_Paz")).isoformat()
        # Escribimos el timestamp en la columna 'Validado' (X)
        sheet.update_cell(cell.row, COL_VALIDADO, timestamp)
        
        # <<< CAMBIO: Añadido el user_id a la respuesta de éxito >>>
        success_response = {
            "status": "success",
            "message": "Acceso permitido",
            "ticket_data": {
                "user_name": nombre_asistente,
                "user_id": user_id,
                "scanned_at": timestamp
            }
        }
        return responses.JSONResponse(status_code=200, content=success_response)

    except Exception as e:
        error_response = {
            "status": "error", "error_code": "UPDATE_FAILED",
            "message": f"Error Crítico: No se pudo actualizar el estado de la entrada. Error: {e}"
        }
        raise HTTPException(status_code=500, detail=error_response)
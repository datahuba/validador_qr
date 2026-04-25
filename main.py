# main.py

import os
import json
import gspread
from fastapi import FastAPI, HTTPException, responses
from pydantic import BaseModel
import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from fastapi.middleware.cors import CORSMiddleware

# 1. CARGAR CONFIGURACIÓN
load_dotenv()

# IDs de las 70 entradas generadas con QR = ticket ID (no valor P)
LEGACY_IDS = {
    'ZJ7DIV9H', 'RD5SOWG8', '5N3F9U3M', 'ZICTUOVZ', 'D79SJ7W2',
    'H7B4UA9T', 'Y03BUZ3W', 'CFOZ3DKA', 'RH38SM7B', 'L7B8QHNX',
    'W06X5N8K', 'CM3I0A9R', 'UD7HYE5P', 'G02QZWG0', 'E1R4UXFL',
    'GVO54YUN', '34R2EIPS', '3F1QTZYO', 'GU0MD04Q', '53ON2D9I',
    'JRNP4FX1', 'N4QG4U09', 'B5X13DGU', '8J507N8S', 'KHBC5894',
    'IK8LPDRN', 'EM607Q6R', '3XW76OIF', 'ZVX1R7ZC', 'UMWM3ZQ5',
    'MWV90ZZM', 'LB4NI8MM', 'BYRKRXXZ', 'PO9QM97B', 'Z40HUWAV',
    'YO0TO8R3', 'FW5ZVEH5', '717ZFXJH', '1U0KCK8E', 'BWMZ553Q',
    'THVPG6IV', '2SYRUWU4', 'PEKP35AH', 'XDW9GR0M', '50KEPSRD',
    'LXD4BUNC', '8BLJQD8U', 'J0OH2QNN', 'U5NNFDRQ', 'FFZFUEP2',
    'PCF2GCMW', '7FG7N3IL', 'V4VVX8DF', '9OUDNKZU', 'F3ZD7N7K',
    'LYZUUO4R', 'KAHHXU8R', 'U4SH8IP3', '7HT8GOMQ', 'D3RKVXVX',
    'FBQ5W8L9', '4R5L8EOH', '677W604J', 'MFDVCMCH', 'GCA1PMFE',
    'D84NJGGX', '7KV8HB15', 'F0TYP804', 'CP0MBKBW', 'Z1J9LOW6',
}

# 2. CONEXIÓN SEGURA CON GOOGLE SHEETS
try:
    creds_json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json_str:
        creds_dict = json.loads(creds_json_str)
        client = gspread.service_account_from_dict(creds_dict)
    else:
        SECRET_FILE_PATH = os.getenv("SECRET_FILE_PATH_LOCAL", "credentials.json")
        client = gspread.service_account(filename=SECRET_FILE_PATH)
except FileNotFoundError as e:
    raise RuntimeError(f"Error Crítico: No se encontró el archivo de credenciales. Error: {e}")
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
    version="4.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Ticket(BaseModel):
    f1_code: str

@app.post("/validate-ticket", tags=["Validación"])
def validate_ticket(ticket: Ticket):
    code = str(ticket.f1_code).strip()

    # Entradas legacy: QR contiene el ID → buscar en columna A (1)
    # Resto: QR contiene el valor P (F1×F2) → buscar en columna J (10)
    search_column = 1 if code in LEGACY_IDS else 10

    try:
        cell = sheet.find(code, in_column=search_column)
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

    COL_USER_ID = 1   # Columna A
    COL_NOMBRE = 2    # Columna B
    COL_VALIDADO = 19 # Columna S

    user_id = row_data[COL_USER_ID - 1] if len(row_data) >= COL_USER_ID else "N/A"
    nombre_asistente = row_data[COL_NOMBRE - 1] if len(row_data) >= COL_NOMBRE else "N/A"
    estado_validacion = row_data[COL_VALIDADO - 1] if len(row_data) >= COL_VALIDADO else ""

    # --- Escenario 2: Entrada YA REGISTRADA ---
    if estado_validacion:
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
        sheet.update_cell(cell.row, COL_VALIDADO, timestamp)

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

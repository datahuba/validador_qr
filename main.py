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
# Carga las variables de entorno desde el archivo .env (para desarrollo local)
load_dotenv()

# 2. CONEXIÓN SEGURA CON GOOGLE SHEETS
# --------------------------------------------------------------------------

# Define los "scopes" o permisos que necesitamos para leer/escribir
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]


try:
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        "credentials.json", # El nombre del Secret File que creaste en Render
        scope
    )
    client = gspread.authorize(creds)
except FileNotFoundError:
    raise RuntimeError("Error Crítico: No se encontró el archivo 'credentials.json'. Asegúrate de que el archivo existe en tu carpeta local o que está configurado correctamente como un 'Secret File' en Render.")
except Exception as e:
    raise RuntimeError(f"Error al cargar las credenciales desde 'credentials.json'. El contenido del JSON podría ser inválido. Error: {e}")


# Abre la hoja de cálculo por su ID (más seguro que por nombre)
sheet_id = os.getenv("GOOGLE_SHEET_ID")
if not sheet_id:
    raise ValueError("Error Crítico: La variable de entorno GOOGLE_SHEET_ID no está configurada.")

try:
    sheet = client.open_by_key(sheet_id).sheet1
except gspread.exceptions.SpreadsheetNotFound:
    raise RuntimeError(f"No se pudo encontrar la hoja de cálculo con ID '{sheet_id}'. Verifica el ID y que hayas compartido la hoja con el email de la cuenta de servicio.")
except Exception as e:
    raise RuntimeError(f"Ocurrió un error al abrir Google Sheet. Error: {e}")

# 3. LÓGICA DE LA API CON FASTAPI
# --------------------------------------------------------------------------

app = FastAPI(
    title="API Validador de Entradas",
    description="API para validar entradas de un evento usando Google Sheets como base de datos.",
    version="1.0.0"
)

# Modelo de datos para la petición que llegará desde el frontend
class Ticket(BaseModel):
    f1_code: int

@app.post("/validate-ticket", tags=["Validación"])
def validate_ticket(ticket: Ticket):
    """
    Valida una entrada buscando su código F1 en la hoja de cálculo.
    - **Busca** el código F1.
    - **Verifica** si la entrada ya ha sido utilizada.
    - **Marca** la entrada como utilizada si la validación es exitosa.
    - **Devuelve** los datos del asistente o un mensaje de error.
    """
    try:
        # Busca el código F1 en la columna 6 (F)
        cell = sheet.find(str(ticket.f1_code), in_column=11)
    except gspread.exceptions.CellNotFound:
        raise HTTPException(status_code=404, detail="ENTRADA INVÁLIDA: El código no existe en la base de datos.")
    except Exception as e:
        # Captura otros posibles errores de conexión durante la búsqueda
        raise HTTPException(status_code=503, detail=f"Error de comunicación con Google Sheets: {e}")

    # Si encontramos la celda, obtenemos toda la fila para acceder a otros datos
    row_data = sheet.row_values(cell.row)

    # Definimos los índices de las columnas para fácil acceso (A=1, B=2, S=19)
    COL_NOMBRE = 2
    COL_VALIDADO = 24

    # Extraemos los datos de la fila de forma segura
    estado_validacion = row_data[COL_VALIDADO - 1] if len(row_data) >= COL_VALIDADO else ""
    nombre_asistente = row_data[COL_NOMBRE - 1] if len(row_data) >= COL_NOMBRE else "Asistente no encontrado"

    # Verificamos si la celda 'Validado' ya tiene contenido (ej. '1')
    if estado_validacion:
        raise HTTPException(
            status_code=409,  # 409 Conflict: la solicitud no se pudo completar debido a un conflicto
            detail=f"ENTRADA RECHAZADA: Este código ya fue utilizado."
        )

    # Si llegamos aquí, la entrada es VÁLIDA y no ha sido usada.
    try:
        # Marcamos la entrada como utilizada escribiendo '1' en la columna 'Validado'
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sheet.update_cell(cell.row, COL_VALIDADO, '1')

        # Devolvemos una respuesta de éxito con los datos del asistente
        return {
            "status": "success",
            "message": "ACCESO AUTORIZADO",
            "data": {
                "nombre": nombre_asistente,
                "hora_validacion": timestamp
            }
        }
    except Exception as e:
        # Este es un error crítico: la entrada era válida pero no pudimos marcarla
        raise HTTPException(status_code=500, detail=f"Error Crítico: No se pudo actualizar el estado de la entrada. Por favor, inténtelo de nuevo. Error: {e}")
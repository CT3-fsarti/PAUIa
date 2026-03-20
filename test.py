import os
import shutil
import json
import subprocess
import vertexai
import re
import unicodedata
from vertexai.generative_models import GenerativeModel, Part
from google.cloud import storage 

# ==========================================
# 1. CONFIGURACIÓN DEL ENTORNO
# ==========================================
PROJECT_ID = "paula-490208"
LOCATION = "us-central1"
BUCKET_NAME = "pau_ia"

ruta_z = r"Z:\07b FRANCISCO\PAUIa"
ruta_a = r"A:\07b FRANCISCO\PAUIa"
disco_base = ruta_z if os.path.exists(ruta_z) else ruta_a

directorio_del_script = os.path.dirname(os.path.abspath(__file__))
ruta_llave = os.path.join(directorio_del_script, "llave-pauia.json")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ruta_llave

DIR_ENTRADA = os.path.join(disco_base, "03_Material para colocar")
DIR_SALIDA = os.path.join(disco_base, "02_Biblioteca_Bucket")
ARCHIVO_JSONL = os.path.join(DIR_SALIDA, "metadata.jsonl")

vertexai.init(project=PROJECT_ID, location=LOCATION)

instrucciones_sistema = """Analiza el PDF y devuelve SOLO JSON en MAYUSCULAS y SIN TILDES. 
Patron nombre: CODIGO_TIPO_AÑO_DETALLE.PDF. Codigos: HIS, MAT2, FIS, QUIM, BIO, LEN, ING, FIL, ECO, DT.
Ejemplo de salida: {"nuevo_nombre": "HIS_APUNTES_2026_TEMA1.PDF", "materia": "HISTORIA"}"""

modelo_bibliotecario = GenerativeModel("gemini-2.5-pro", system_instruction=instrucciones_sistema)

# ==========================================
# 2. FUNCIONES DE APOYO (REFORZADAS)
# ==========================================
def limpiar_texto(texto):
    if not texto: return ""
    texto = str(texto).upper()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = re.sub(r'[^A-Z0-9_.]', '_', texto)
    return re.sub(r'_{2,}', '_', texto).strip('_')

def analizar_pdf(ruta_pdf, contexto):
    with open(ruta_pdf, "rb") as f:
        datos_pdf = Part.from_data(data=f.read(), mime_type="application/pdf")
    
    respuesta = modelo_bibliotecario.generate_content([datos_pdf, f"Analiza este archivo de la carpeta: {contexto}"])
    texto_raw = respuesta.text
    
    # --- LIMPIEZA DE JSON AGRESIVA ---
    # Buscamos lo que haya entre la primera '{' y la última '}'
    match = re.search(r'\{.*\}', texto_raw, re.DOTALL)
    if match:
        json_limpio = match.group(0)
        return json.loads(json_limpio)
    else:
        # Si no hay llaves, lanzamos error personalizado
        raise ValueError(f"La IA no devolvió un JSON válido. Respuesta: {texto_raw}")

# ==========================================
# 3. EJECUCIÓN RECURSIVA INTEGRADA
# ==========================================
def procesar_biblioteca_completa():
    print(f"🚀 Buscando material en: {DIR_ENTRADA} y subcarpetas...")
    
    if not os.path.exists(DIR_SALIDA):
        os.makedirs(DIR_SALIDA)

    archivos_encontrados = []
    for raiz, directorios, archivos in os.walk(DIR_ENTRADA):
        for nombre_f in archivos:
            if nombre_f.lower().endswith(".pdf"):
                archivos_encontrados.append(os.path.join(raiz, nombre_f))
    
    if not archivos_encontrados:
        print("📭 No hay archivos PDF nuevos.")
    else:
        print(f"📂 Detectados {len(archivos_encontrados)} archivos.")
        for ruta_full_entrada in archivos_encontrados:
            nombre_original = os.path.basename(ruta_full_entrada)
            carpeta_origen = os.path.basename(os.path.dirname(ruta_full_entrada))
            
            print(f"\n🧠 Analizando: {nombre_original}...")
            
            try:
                resultado = analizar_pdf(ruta_full_entrada, carpeta_origen)
                nombre_sugerido = limpiar_texto(resultado.get("nuevo_nombre", nombre_original))
                if not nombre_sugerido.upper().endswith(".PDF"):
                    nombre_sugerido += ".PDF"
                
                ruta_full_salida = os.path.join(DIR_SALIDA, nombre_sugerido)
                doc_id = nombre_sugerido.replace(".PDF", "").replace(".pdf", "")

                metadatos_limpios = {k: limpiar_texto(v) for k, v in resultado.items() if k != "nuevo_nombre"}
                metadatos_limpios["carpeta_origen"] = limpiar_texto(carpeta_origen)
                
                registro = {
                    "id": doc_id,
                    "structData": metadatos_limpios,
                    "content": {
                        "mimeType": "application/pdf",
                        "uri": f"gs://{BUCKET_NAME}/{nombre_sugerido}"
                    }
                }

                with open(ARCHIVO_JSONL, "a", encoding="utf-8") as f_jsonl:
                    f_jsonl.write(json.dumps(registro, ensure_ascii=False) + "\n")
                
                if os.path.exists(ruta_full_salida):
                    os.remove(ruta_full_salida)
                shutil.move(ruta_full_entrada, ruta_full_salida)
                print(f"  ✅ Procesado: {nombre_sugerido}")

            except Exception as e:
                print(f"  ❌ Error con {nombre_original}: {e}")

    # Sincronización y Verificación (Tu método exitoso)
    print(f"\n☁️ Sincronizando...")
    subprocess.run(f'gcloud storage rsync "{DIR_SALIDA}" gs://{BUCKET_NAME} --recursive', shell=True)

    print(f"\n🔍 VERIFICACIÓN FINAL:")
    try:
        cliente = storage.Client(project=PROJECT_ID)
        bucket = cliente.bucket(BUCKET_NAME) 
        blobs = list(bucket.list_blobs(max_results=15))
        for blob in blobs:
            print(f"   - {blob.name} ({round(blob.size/1024, 1)} KB)")
        print("\n✨ ¡TODO EN ORDEN!")
    except Exception as e:
        print(f"❌ Error verificación: {e}")

if __name__ == "__main__":
    procesar_biblioteca_completa()

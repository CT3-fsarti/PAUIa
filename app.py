import streamlit as st
import vertexai
import json
import os
from google.oauth2 import service_account
from google.cloud import storage 
from vertexai.generative_models import GenerativeModel, Part, Tool, grounding

# ==========================================
# 0. CONFIGURACIÓN INICIAL Y DATOS USUARIO
# ==========================================
nombre_usuario = "Paco" # Nombre para personalizar la experiencia
PROJECT_ID = "paula-490208"
BUCKET_NAME = "pau_ia"

st.set_page_config(page_title="PAUIa - Tu Tutora PAU", page_icon="👩‍🏫", layout="centered")

# --- DISEÑO CSS PARA GENERACIÓN Z ---
estilo_css = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    .stApp {
        background-color: #F8FAFC;
    }
    
    h1, h2, h3 {
        color: #1E3A8A !important;
        font-family: 'Inter', sans-serif;
    }
    
    .stButton>button {
        border-radius: 20px !important;
        background-color: #F59E0B !important;
        color: white !important;
        border: none !important;
        font-weight: bold !important;
        transition: all 0.3s ease;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #D97706 !important;
        box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3) !important;
        transform: translateY(-2px);
    }

    .user-avatar {
        width: 50px;
        height: 50px;
        background-color: #1E3A8A;
        color: white;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 20px;
        margin-bottom: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    /* Estilo para las tarjetas del gestor */
    .upload-card {
        background-color: white;
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #E2E8F0;
        margin-top: 10px;
    }
</style>
"""
st.markdown(estilo_css, unsafe_allow_html=True)

# ==========================================
# 1. GESTIÓN DE CREDENCIALES Y BUCKET
# ==========================================
@st.cache_resource
def cargar_credenciales():
    if "google_cloud" in st.secrets:
        creds_dict = json.loads(st.secrets["google_cloud"]["credentials"])
        return service_account.Credentials.from_service_account_info(creds_dict)
    else:
        archivo_local = "llave-pauia.json" 
        if os.path.exists(archivo_local):
            return service_account.Credentials.from_service_account_file(archivo_local)
        st.error("❌ No encuentro el archivo de llaves local.")
        st.stop()

llave_maestra = cargar_credenciales()

@st.cache_data(ttl=3600)
def obtener_asignaturas_del_bucket(_credenciales):
    try:
        cliente_storage = storage.Client(project=PROJECT_ID, credentials=_credenciales)
        bucket = cliente_storage.bucket(BUCKET_NAME)
        blobs = bucket.list_blobs()
        
        asignaturas = set()
        for blob in blobs:
            if not blob.name.endswith('/'):
                partes = blob.name.split('/')
                if len(partes) > 1:
                    nombre_carpeta = partes[-2] 
                    asignaturas.add(nombre_carpeta.replace("_", " "))
                    
        return sorted(list(asignaturas)) if asignaturas else ["Matemáticas II"]
    except Exception as e:
        return [f"Error leyendo bucket: {e}"]

lista_asignaturas = obtener_asignaturas_del_bucket(llave_maestra)

# --- FUNCIONES NUEVAS PARA EL GESTOR ---
def subir_pdf_a_storage(file_bytes, nombre_archivo, carpeta):
    """Sube el archivo directamente al Bucket de Google"""
    cliente = storage.Client(project=PROJECT_ID, credentials=llave_maestra)
    bucket = cliente.bucket(BUCKET_NAME)
    ruta_final = f"{carpeta.replace(' ', '_')}/{nombre_archivo}"
    blob = bucket.blob(ruta_final)
    blob.upload_from_string(file_bytes, content_type="application/pdf")
    return f"gs://{BUCKET_NAME}/{ruta_final}"

# ==========================================
# 2. PANEL LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
    col_av, col_txt = st.columns([1, 3])
    with col_av:
        st.markdown(f'<div class="user-avatar">{nombre_usuario[0]}</div>', unsafe_allow_html=True)
    with col_txt:
        st.markdown(f"**Usuario:** {nombre_usuario}")
        st.caption("Plan Premium ⭐")
    
    st.markdown("---")
    
    try:
        st.image("logo_pauia.png", use_container_width=True)
    except:
        pass

    st.title("⚙️ Ajustes de estudio")
    
    comunidad = st.selectbox("📍 ¿Dónde te examinas?", ["Madrid", "Andalucía", "Cataluña", "Valencia", "Galicia", "Otras"])
    asignatura = st.selectbox("📚 ¿Qué repasamos hoy?", lista_asignaturas)
    
    if "config" not in st.session_state:
        st.session_state.config = {"ccaa": comunidad, "sub": asignatura}
    
    if comunidad != st.session_state.config["ccaa"] or asignatura != st.session_state.config["sub"]:
        st.session_state.config = {"ccaa": comunidad, "sub": asignatura}
        st.session_state.mensajes = []
        st.rerun()

    st.markdown("---")
    if st.button("✨ Limpiar y empezar de cero"):
        st.session_state.mensajes = []
        st.rerun()

# ==========================================
# 3. MOTOR DE INTELIGENCIA ARTIFICIAL
# ==========================================
@st.cache_resource
def iniciar_chat(ccaa, sub, _creds, usuario):
    try:
        vertexai.init(project=PROJECT_ID, location="us-central1", credentials=_creds)
        
        herramienta_rag = Tool.from_retrieval(
            retrieval=grounding.Retrieval(
                source=grounding.VertexAISearch(
                    datastore="pauia_1773486206667_gcs_store",
                    project=PROJECT_ID,
                    location="global"
                )
            )
        )
        
        instrucciones = f"""Eres PAUIa, una tutora virtual joven, empática y experta en PAU.
        Ayudas a {usuario} a preparar {sub} en {ccaa}.
        
        ESTILO:
        1. Tuteo, tono motivador y uso de emojis 🚀.
        2. Personaliza: usa el nombre '{usuario}' para que sienta que la tutoría es 1 a 1.
        3. Didáctica: explica paso a paso y cita la fuente oficial.
        
        REGLA DE ORO: Responde ÚNICAMENTE con la información de tus documentos. 
        Si no está en el manual, dile a {usuario} de forma amable que no tienes ese dato pero que siga dándole caña al estudio."""

        modelo = GenerativeModel(
            model_name="gemini-2.5-pro",
            tools=[herramienta_rag],
            system_instruction=instrucciones,
            generation_config={"temperature": 0.0}
        )
        return modelo.start_chat(), None
    except Exception as e:
        return None, str(e)

chat_sesion, error_ia = iniciar_chat(comunidad, asignatura, llave_maestra, nombre_usuario)

# ==========================================
# 4. INTERFAZ PRINCIPAL CON PESTAÑAS
# ==========================================
st.title("PAUIa")
st.markdown(f"#### 🚀 TU Tutora Experta en PAU <span style='font-size: 14px; color: #666666; font-weight: normal;'>(by Yoel&Fran ©2026)</span>", unsafe_allow_html=True)

# --- CREACIÓN DE PESTAÑAS ---
tab_estudio, tab_gestion = st.tabs(["🙋‍♀️ Estudiar", "📂 Gestionar Documentos"])

# --- PESTAÑA 1: CHAT (Toda tu lógica original) ---
with tab_estudio:
    if error_ia:
        st.error(f"Fallo de conexión: {error_ia}")
    else:
        if "mensajes" not in st.session_state or not st.session_state.mensajes:
            st.session_state.mensajes = [{"role": "assistant", "content": f"¡Hola {nombre_usuario}! 🙋‍♀️ Soy PAUIa. He cargado todo sobre **{asignatura}**. ¿Por dónde quieres empezar a saco hoy? 🚀"}]

        for msg in st.session_state.mensajes:
            avatar = "✌️" if msg["role"] == "user" else "🙋‍♀️"
            with st.chat_message(msg["role"], avatar=avatar):
                st.markdown(msg["content"])

        if prompt := st.chat_input(f"Escribe tu duda, {nombre_usuario}..."):
            with st.chat_message("user", avatar="✌️"):
                st.markdown(prompt)
            st.session_state.mensajes.append({"role": "user", "content": prompt})

            with st.chat_message("assistant", avatar="🙋‍♀️"):
                with st.spinner("Consultando manuales... 📖"):
                    try:
                        res = chat_sesion.send_message(prompt)
                        texto = res.text if hasattr(res, 'text') else "".join([p.text for p in res.candidates[0].content.parts])
                        st.markdown(texto)
                        st.session_state.mensajes.append({"role": "assistant", "content": texto})
                    except Exception as e:
                        st.error(f"¡Ups! Me he liado un poco: {e}")

# --- PESTAÑA 2: GESTOR (Nueva funcionalidad) ---
with tab_gestion:
    st.subheader("📚 Bibliotecaria Virtual")
    st.write("Sube tus archivos PDF y deja que PAUIa los organice en el Bucket.")
    
    archivo_cargado = st.file_uploader("Arrastra aquí un examen o libro (PDF)", type="pdf")
    
    if archivo_cargado:
        # Usamos la misma IA para analizar el archivo cargado
        with st.spinner("Analizando contenido con Gemini 2.5 Pro..."):
            try:
                # Inicializar Vertex para análisis de archivos
                vertexai.init(project=PROJECT_ID, location="us-central1", credentials=llave_maestra)
                modelo_ana = GenerativeModel("gemini-2.5-pro")
                
                # Leer bytes del archivo
                pdf_bytes = archivo_cargado.getvalue()
                pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
                
                prompt_ana = """Analiza este PDF de PAU y devuelve SOLO un objeto JSON con:
                'nuevo_nombre': sugerencia tipo CODIGO_TIPO_AÑO.PDF (ej: HIS_EXAMEN_2025.PDF)
                'materia': La asignatura a la que pertenece."""
                
                respuesta = modelo_ana.generate_content([pdf_part, prompt_ana])
                # Limpiar la respuesta para obtener el JSON
                limpio = respuesta.text.replace("```json", "").replace("```", "").strip()
                info = json.loads(limpio)
                
                # Mostrar propuesta al usuario
                st.markdown(f"""
                <div class="upload-card">
                    <p style='color: #1E3A8A; font-weight: bold;'>🔍 Análisis de PAUIa:</p>
                    <p><b>Nombre sugerido:</b> {info['nuevo_nombre']}</p>
                    <p><b>Asignatura:</b> {info['materia']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Confirmación final
                carpeta_final = st.text_input("Confirmar carpeta de destino en Bucket:", value=info['materia'].replace(" ", "_"))
                
                if st.button("🚀 Subir definitivamente al Bucket"):
                    with st.spinner("Subiendo a Google Cloud Storage..."):
                        uri_final = subir_pdf_a_storage(pdf_bytes, info['nuevo_nombre'], carpeta_final)
                        st.success(f"¡Hecho! Archivo guardado en: {uri_final}")
                        st.balloons()
                        # Nota: Aquí faltaría actualizar el metadata.jsonl si lo usas para Vertex Search
                        
            except Exception as e:
                st.error(f"Error analizando el archivo: {e}")

                def actualizar_metadata_jsonl(nuevo_registro):
    """Descarga, edita y resube el índice metadata.jsonl al bucket"""
    cliente = storage.Client(project=PROJECT_ID, credentials=llave_maestra)
    bucket = cliente.bucket(BUCKET_NAME)
    blob = bucket.blob("metadata.jsonl") # O la ruta donde lo tengas en el bucket

    contenido_actual = ""
    if blob.exists():
        contenido_actual = blob.download_as_text()
    
    # Añadimos la nueva línea (JSONL es una línea por objeto)
    nuevo_contenido = contenido_actual.strip() + "\n" + json.dumps(nuevo_registro, ensure_ascii=False)
    
    blob.upload_from_string(nuevo_contenido.strip(), content_type="application/json")

# --- DENTRO DE TU BOTÓN DE SUBIDA EN LA PESTAÑA DE GESTIÓN ---
if st.button("🚀 Subir definitivamente al Bucket"):
    with st.spinner("Subiendo y actualizando índices..."):
        # 1. Subir el PDF
        uri_final = subir_pdf_a_storage(pdf_bytes, info['nuevo_nombre'], carpeta_final)
        
        # 2. Crear el registro para el JSONL
        doc_id = info['nuevo_nombre'].replace(".PDF", "").replace(".pdf", "")
        registro = {
            "id": doc_id,
            "structData": {
                "materia": info['materia'].upper(),
                "titulo": info['nuevo_nombre'].replace("_", " ")
            },
            "content": {"mimeType": "application/pdf", "uri": uri_final}
        }
        
        # 3. Actualizar el archivo de metadatos en la nube
        actualizar_metadata_jsonl(registro)
        
        st.success(f"¡Todo listo! PDF subido e indexado en metadata.jsonl")
        st.balloons()

        

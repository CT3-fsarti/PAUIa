import streamlit as st
import vertexai
import json
import os
from google.oauth2 import service_account
from google.cloud import storage # <--- NUEVA LIBRERÍA PARA LEER EL BUCKET
from vertexai.generative_models import GenerativeModel, Tool, grounding

# 1. Configuración de la interfaz
st.set_page_config(page_title="PAUIa - Tutor", page_icon="🎓", layout="centered")

# --- SISTEMA CENTRAL DE CREDENCIALES ---
@st.cache_resource
def cargar_credenciales():
    """Carga la llave maestra una sola vez para que la usen todos los servicios"""
    if "google_cloud" in st.secrets:
        creds_dict = json.loads(st.secrets["google_cloud"]["credentials"])
        return service_account.Credentials.from_service_account_info(creds_dict)
    else:
        archivo_local = "llave-pauia.json" 
        if os.path.exists(archivo_local):
            return service_account.Credentials.from_service_account_file(archivo_local)
        st.error("❌ No encuentro el archivo de llaves local.")
        st.stop()

# Guardamos la llave en una variable para usarla ahora
llave_maestra = cargar_credenciales()

# --- LECTOR DINÁMICO DEL BUCKET ---
@st.cache_data(ttl=3600) # Guarda la lista en memoria 1 hora para que la web vaya rapidísima
def obtener_asignaturas_del_bucket(_credenciales):
    try:
        # Nos conectamos al Storage usando tu llave
        cliente_storage = storage.Client(project="paula-490208", credentials=_credenciales)
        bucket = cliente_storage.bucket("pau_ia") # Buscamos en tu bucket real
        blobs = bucket.list_blobs()
        
        asignaturas = set()
        for blob in blobs:
            # Ignoramos si es una carpeta vacía, solo queremos archivos
            if not blob.name.endswith('/'):
                partes = blob.name.split('/')
                # Si el archivo está dentro de una carpeta (ej: 01_Libros/Matematicas_II/apuntes.pdf)
                if len(partes) > 1:
                    # Cogemos la carpeta que contiene el archivo (la penúltima parte de la ruta)
                    nombre_carpeta = partes[-2] 
                    # Lo ponemos bonito (quitamos guiones bajos)
                    nombre_limpio = nombre_carpeta.replace("_", " ")
                    asignaturas.add(nombre_limpio)
                    
        # Devolvemos la lista ordenada alfabéticamente
        return sorted(list(asignaturas)) if asignaturas else ["No se encontraron carpetas"]
    except Exception as e:
        return [f"Error leyendo el bucket: {e}"]

# Obtenemos la lista real de tu Google Cloud
lista_dinamica_asignaturas = obtener_asignaturas_del_bucket(llave_maestra)


# --- PANEL LATERAL (SIDEBAR) ---
with st.sidebar:
    try:
        st.image("logo_pauia.png", use_container_width=True)
    except Exception:
        pass 
    
    st.title("🎓 Configuración")
    
    # 1. Menús desplegables
    comunidad = st.selectbox(
        "📍 Comunidad Autónoma",
        ["Madrid", "Andalucía", "Cataluña", "Comunidad Valenciana", "Galicia", "Castilla y León", "Todas"]
    )
    
    # ¡AQUÍ ESTÁ LA MAGIA! Le pasamos la lista que hemos leído de tu bucket
    asignatura = st.selectbox(
        "📚 Asignatura",
        lista_dinamica_asignaturas
    )
    
    # 2. Control de cambios para limpiar el chat si cambian de tema
    if "comunidad_actual" not in st.session_state:
        st.session_state.comunidad_actual = comunidad
        st.session_state.asignatura_actual = asignatura
        
    if comunidad != st.session_state.comunidad_actual or asignatura != st.session_state.asignatura_actual:
        st.session_state.comunidad_actual = comunidad
        st.session_state.asignatura_actual = asignatura
        st.session_state.mensajes = [] 
        st.rerun() 

    st.markdown("---")
    st.info("PAUIa busca información exclusivamente en los manuales oficiales de la asignatura seleccionada.")
    
    if st.button("🗑️ Limpiar conversación"):
        st.session_state.mensajes = []
        st.rerun()
# -------------------------------

# --- TÍTULO PRINCIPAL ---
st.title("🎓 PAUIa")
st.caption("🚀 TU Tutor Experto en PAU | Potenciado por Gemini 2.5 Pro")

# 2. Conexión blindada de la IA
@st.cache_resource
def iniciar_chat(comunidad_elegida, asignatura_elegida, _credenciales): 
    try:
        # Iniciamos la IA usando la misma llave maestra
        vertexai.init(project="paula-490208", location="us-central1", credentials=_credenciales) 
        
        herramienta_rag = Tool.from_retrieval(
            retrieval=grounding.Retrieval(
                source=grounding.VertexAISearch(
                    datastore="pauia_1773486206667_gcs_store",
                    project="paula-490208",
                    location="global"
                )
            )
        )
        
        # Instrucciones dinámicas con la asignatura leída del bucket
        instrucciones = f"""Eres PAUIa, el asistente inteligente experto en preparación de exámenes PAU.
        Tu misión es ayudar a los alumnos a preparar la asignatura de {asignatura_elegida} para la Comunidad Autónoma de {comunidad_elegida}.
        
        REGLA DE ORO INQUEBRANTABLE: 
        TIENES ESTRICTAMENTE PROHIBIDO usar tu conocimiento general, interno o de internet. 
        DEBES responder ÚNICA y EXCLUSIVAMENTE con la información exacta extraída de los documentos de tu herramienta de búsqueda (Data Store).
        
        Si el alumno te pregunta algo que no aparece en tus documentos, tu respuesta OBLIGATORIA y literal debe ser: "No tengo esa información en mis manuales oficiales." No des ninguna explicación adicional.
        Si encuentras la respuesta en los documentos, menciona de dónde la has sacado."""
        
        modelo = GenerativeModel(
            model_name="gemini-2.5-pro", 
            tools=[herramienta_rag],
            system_instruction=instrucciones,
            generation_config={"temperature": 0.0} 
        )
        
        return modelo.start_chat(), None
    except Exception as e:
        return None, str(e)

# 3. Arrancamos el motor
chat_sesion, error_conexion = iniciar_chat(comunidad, asignatura, llave_maestra)

if error_conexion:
    st.error("⚠️ Hubo un problema al arrancar PAUIa:")
    st.code(error_conexion)
else:
    if "mensajes" not in st.session_state or len(st.session_state.mensajes) == 0:
        st.session_state.mensajes = [{"role": "assistant", "content": "¡Hola! Soy PAUIa. ¿Con qué parte del temario o examen de la PAU te ayudo hoy?"}]

    for msg in st.session_state.mensajes:
        icono = "🧑‍🎓" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=icono):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Escribe aquí tu pregunta..."):
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(prompt)
        st.session_state.mensajes.append({"role": "user", "content": prompt})

        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Buscando en los apuntes..."):
                try:
                    respuesta = chat_sesion.send_message(prompt)
                    try:
                        texto_final = respuesta.text
                    except Exception:
                        texto_final = "".join([part.text for part in respuesta.candidates[0].content.parts])
                    
                    st.markdown(texto_final)
                    st.session_state.mensajes.append({"role": "assistant", "content": texto_final})
                except Exception as e:
                    st.error(f"Error al generar la respuesta: {e}")

import streamlit as st
import vertexai
import json
import os
from google.oauth2 import service_account
from vertexai.generative_models import GenerativeModel, Tool, grounding

# 1. Configuración de la interfaz
st.set_page_config(page_title="PAUIa - Tutor", page_icon="🎓", layout="centered")

# --- PANEL LATERAL (SIDEBAR) ---
with st.sidebar:
    # Intentamos cargar el logo (asegúrate de que el archivo se llama exactamente así y está en la misma carpeta)
    try:
        st.image("logo_pauia.png", use_container_width=True)
    except Exception:
        pass # Si la imagen no está o tiene otro nombre (como .jpg), no pasa nada, la app sigue funcionando
    
    st.title("🎓 Sobre PAUIa")
    st.info(
        "PAUIa es tu asistente inteligente para preparar la selectividad. "
        "Busca información exclusivamente en los manuales oficiales y exámenes de convocatorias anteriores."
    )
    st.markdown("---")
    # Botón para limpiar el chat sin tener que recargar la web entera
    if st.button("🗑️ Limpiar conversación"):
        st.session_state.mensajes = []
        st.rerun()
# -------------------------------

# --- TÍTULO PRINCIPAL ---
st.title("🎓 PAUIa")
st.caption("🚀 TU Tutor Experto en PAU | Potenciado por Gemini 2.5 Pro")

# 2. Conexión blindada con Google Cloud
@st.cache_resource
def iniciar_chat():
    try:
        # PASO A: Obtenemos la llave de forma directa (Modo Nube o Modo Local)
        if "google_cloud" in st.secrets:
            creds_dict = json.loads(st.secrets["google_cloud"]["credentials"])
            credenciales = service_account.Credentials.from_service_account_info(creds_dict)
        else:
            archivo_local = "llave-pauia.json" # Tu llave en el PC
            if not os.path.exists(archivo_local):
                return None, f"No encuentro el archivo de llaves: {archivo_local}"
            credenciales = service_account.Credentials.from_service_account_file(archivo_local)

        # PASO B: Iniciamos Vertex AI con la llave
        vertexai.init(project="paula-490208", location="us-central1", credentials=credenciales) 
        
        # Conectamos tu Datastore (RAG)
        herramienta_rag = Tool.from_retrieval(
            retrieval=grounding.Retrieval(
                source=grounding.VertexAISearch(
                    datastore="pauia_1773486206667_gcs_store",
                    project="paula-490208",
                    location="global"
                )
            )
        )
        
        # Configuramos la IA: Reglas militares anti-alucinaciones
        instrucciones = """Eres PAUIa, el asistente inteligente experto en preparación de exámenes PAU.
        Tu misión es ayudar a los alumnos a preparar la PAU de matemáticas.
        
        REGLA DE ORO INQUEBRANTABLE: 
        TIENES ESTRICTAMENTE PROHIBIDO usar tu conocimiento general, interno o de internet. 
        DEBES responder ÚNICA y EXCLUSIVAMENTE con la información exacta extraída de los documentos de tu herramienta de búsqueda (Data Store).
        
        Si el alumno te pregunta algo que no aparece en tus documentos, tu respuesta OBLIGATORIA y literal debe ser: "No tengo esa información en mis manuales oficiales." No des ninguna explicación adicional ni intentes responder la pregunta.
        
        Si encuentras la respuesta en los documentos, menciona de dónde la has sacado."""
        
        modelo = GenerativeModel(
            model_name="gemini-2.5-pro", 
            tools=[herramienta_rag],
            system_instruction=instrucciones,
            generation_config={"temperature": 0.0} # Creatividad al mínimo para evitar invenciones
        )
        
        return modelo.start_chat(), None
    except Exception as e:
        return None, str(e)

# 3. Arrancamos el motor
chat_sesion, error_conexion = iniciar_chat()

# Mostramos errores técnicos si los hay
if error_conexion:
    st.error("⚠️ Hubo un problema al arrancar PAUIa:")
    st.code(error_conexion)
else:
    # --- MENSAJE DE BIENVENIDA ---
    if "mensajes" not in st.session_state or len(st.session_state.mensajes) == 0:
        st.session_state.mensajes = [{"role": "assistant", "content": "¡Hola! Soy PAUIa. ¿Con qué parte del temario o examen de la PAU te ayudo hoy?"}]

    # --- HISTORIAL DE CHAT CON AVATARES ---
    for msg in st.session_state.mensajes:
        icono = "🧑‍🎓" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=icono):
            st.markdown(msg["content"])

    # --- CAJA DE TEXTO PRINCIPAL ---
    if prompt := st.chat_input("Escribe aquí tu pregunta sobre el temario..."):
        
        # 1. Mostramos la pregunta del usuario
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(prompt)
        st.session_state.mensajes.append({"role": "user", "content": prompt})

        # 2. Mostramos la respuesta de PAUIa
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Buscando en los apuntes..."):
                try:
                    respuesta = chat_sesion.send_message(prompt)
                    
                    # Unimos los fragmentos por si Google manda la respuesta "a trozos"
                    try:
                        texto_final = respuesta.text
                    except Exception:
                        texto_final = "".join([part.text for part in respuesta.candidates[0].content.parts])
                    
                    st.markdown(texto_final)
                    st.session_state.mensajes.append({"role": "assistant", "content": texto_final})
                except Exception as e:
                    st.error(f"Error al generar la respuesta: {e}")

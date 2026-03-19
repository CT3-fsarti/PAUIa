import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Tool, grounding

# 1. Configuración de la interfaz limpia
st.set_page_config(page_title="PAUIa", page_icon="🎓", layout="centered")
st.title("🎓 PAUIa")
st.write("Tu asistente experto para la preparación de exámenes PAU.")

# 2. Conexión segura con Google Cloud
@st.cache_resource
def iniciar_chat():
    try:
        # Iniciamos tu proyecto principal
        vertexai.init(project="paula-490208", location="us-central1") 
        
        # Conectamos tu Datastore (RAG)
        herramienta_rag = Tool.from_retrieval(
            retrieval=grounding.Retrieval(
                source=grounding.VertexAISearch(
                    datastore="pauia_1773486206667_gcs_store", # Tu ID de PDFs
                    project="paula-490208",                    # Tu Proyecto real
                    location="global"                          # La región de los PDFs
                )
            )
        )
        
        # Configuramos la IA sin inventos
        instrucciones = """Eres PAUIa, el asistente inteligente experto en preparación de exámenes PAU.
        Tu misión es ayudar a los alumnos a preparar la PAU de forma eficiente y cercana.
        Responde siempre utilizando la información de las herramientas de búsqueda (Data Store).
        Si encuentras la respuesta en un documento, menciona de dónde la has sacado para que el alumno sepa dónde profundizar.
        Si la pregunta no puede responderse con los documentos proporcionados, di: "No tengo esa información en mis manuales oficiales"."""
        
        modelo = GenerativeModel(
            model_name="gemini-2.5-pro", 
            tools=[herramienta_rag],
            system_instruction=instrucciones
        )
        
        return modelo.start_chat(), None
    except Exception as e:
        return None, str(e)

# 3. Arrancamos el motor
chat_sesion, error_conexion = iniciar_chat()

# Si hay error, lo mostramos en pantalla
if error_conexion:
    st.error("⚠️ Hubo un problema al conectar con Google Cloud:")
    st.code(error_conexion)
else:
    # Si todo va bien, mostramos el chat
    if "mensajes" not in st.session_state:
        st.session_state.mensajes = []

    # Pintamos el historial
    for msg in st.session_state.mensajes:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Caja de texto para hablar con PAUIa
    if prompt := st.chat_input("Pregúntame algo sobre el temario de la PAU..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.mensajes.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("Consultando los manuales..."):
                try:
                    respuesta = chat_sesion.send_message(prompt)
                    st.markdown(respuesta.text)
                    st.session_state.mensajes.append({"role": "assistant", "content": respuesta.text})
                except Exception as e:
                    st.error(f"Error al generar la respuesta: {e}")

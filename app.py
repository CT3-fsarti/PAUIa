import streamlit as st
import vertexai
import json
import os
from google.oauth2 import service_account
from google.cloud import storage 
from vertexai.generative_models import GenerativeModel, Tool, grounding

nombre_usuario = "Paco" # Esto luego lo podremos sacar de una base de datos

# 1. Configuración de la interfaz
st.set_page_config(page_title="PAUIa - Tu Tutora PAU", page_icon="👩‍🏫", layout="centered")

# --- MAGIA CSS: ESTILO MODERNO Y JOVEN ---
estilo_css = """
<style>
    /* Ocultar el menú por defecto y el pie de página de Streamlit para que parezca una App real */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Fondo de la app: Un gris/azulado súper claro, no blanco nuclear (cansa menos la vista) */
    .stApp {
        background-color: #F8FAFC;
    }
    
    /* Títulos principales con el Azul oscuro de tu logo */
    h1, h2, h3 {
        color: #1E3A8A !important;
        font-family: 'Inter', sans-serif;
    }
    
    /* Estilizar el botón de "Limpiar conversación" con el color dorado/ámbar del logo */
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

    /* Sombras suaves en los menús desplegables */
    div[data-baseweb="select"] > div {
        border-radius: 10px;
        border-color: #E2E8F0;
        box-shadow: 0 2px 5px rgba(0,0,0,0.02);
    }

    /* Estilo para el avatar de usuario circular */
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
</style>
"""
st.markdown(estilo_css, unsafe_allow_html=True)
# ----------------------------------------

# --- SISTEMA CENTRAL DE CREDENCIALES ---
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

# --- LECTOR DINÁMICO DEL BUCKET ---
@st.cache_data(ttl=3600)
def obtener_asignaturas_del_bucket(_credenciales):
    try:
        cliente_storage = storage.Client(project="paula-490208", credentials=_credenciales)
        bucket = cliente_storage.bucket("pau_ia")
        blobs = bucket.list_blobs()
        
        asignaturas = set()
        for blob in blobs:
            if not blob.name.endswith('/'):
                partes = blob.name.split('/')
                if len(partes) > 1:
                    nombre_carpeta = partes[-2] 
                    nombre_limpio = nombre_carpeta.replace("_", " ")
                    asignaturas.add(nombre_limpio)
                    
        return sorted(list(asignaturas)) if asignaturas else ["No se encontraron carpetas"]
    except Exception as e:
        return [f"Error leyendo el bucket: {e}"]

lista_dinamica_asignaturas = obtener_asignaturas_del_bucket(llave_maestra)

# --- PANEL LATERAL (SIDEBAR) ---
with st.sidebar:

    # --- SECCIÓN DE PERFIL DE USUARIO ---
    col1, col2 = st.columns([1, 3])
    with col1:
        # Aquí simulamos el icono circular con HTML
        st.markdown('<div class="user-avatar">P</div>', unsafe_allow_html=True)
    with col2:
        st.markdown("**Usuario:** Paco")
        st.caption("Plan Premium ⭐")
    
    st.markdown("---")
    
    # El resto de tu código del sidebar (Logo, selectbox, etc.) sigue igual...
    try:
        st.image("logo_pauia.png", use_container_width=True)
    except Exception:
        pass

    st.title("⚙️ Ajustes de estudio")
    
    comunidad = st.selectbox(
        "📍 ¿Dónde te examinas?",
        ["Madrid", "Andalucía", "Cataluña", "Comunidad Valenciana", "Galicia", "Castilla y León", "Todas"]
    )
    
    asignatura = st.selectbox(
        "📚 ¿Qué repasamos hoy?",
        lista_dinamica_asignaturas
    )
    
    if "comunidad_actual" not in st.session_state:
        st.session_state.comunidad_actual = comunidad
        st.session_state.asignatura_actual = asignatura
        
    if comunidad != st.session_state.comunidad_actual or asignatura != st.session_state.asignatura_actual:
        st.session_state.comunidad_actual = comunidad
        st.session_state.asignatura_actual = asignatura
        st.session_state.mensajes = [] 
        st.rerun() 

    st.markdown("---")
    st.caption("Solo uso apuntes y exámenes oficiales. ¡Cero inventos! 😉")
    
    if st.button("✨ Limpiar y empezar de cero"):
        st.session_state.mensajes = []
        st.rerun()
# -------------------------------

# --- TÍTULO PRINCIPAL ---
st.title("PAUIa")
st.markdown("#### 🚀 TU Tutora Experta en PAU <span style='font-size: 16px; color: #666666; font-weight: normal;'>(by Yoel&Fran ©2026)</span>", unsafe_allow_html=True)

# 2. Conexión blindada de la IA
@st.cache_resource
def iniciar_chat(comunidad_elegida, asignatura_elegida, _credenciales): 
    try:
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
        
        instrucciones = f"""Eres PAUIa (pronunciado como el nombre Paula), una tutora virtual joven, cercana, empática y muy inteligente.
        Tu misión es ayudar a estudiantes de Bachillerato (16-18 años) a preparar la PAU de {asignatura_elegida} en {comunidad_elegida}.

        ESTILO
            1. Háblales de tú, con un tono motivador, claro y usando emojis moderadamente.
            2. Quítales el estrés del examen.
            3. Usa su nombre de vez en cuando para que sienta que la tutoría es 1 a 1. Por ejemplo: '¡Muy buena pregunta, {nombre_usuario}! Vamos a resolverlo...'
            4. Si encuentras la respuesta, explícala paso a paso de forma didáctica y menciona de qué documento la has sacado.
        
        REGLAS DE ORO INQUEBRANTABLES: 
            1. DEBES responder ÚNICA y EXCLUSIVAMENTE con la información exacta extraída de los documentos de tu herramienta de búsqueda.
            2. Si el alumno te pregunta algo que no aparece en tus documentos, responde de forma amable pero firme: "¡Ups! 😅 No tengo esa información en mis apuntes de {asignatura_elegida}. ¡Intenta preguntarme sobre otra parte del temario!"
        
        

     """
        
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
    st.error("⚠️ Ups, problemas técnicos al conectar con el servidor:")
    st.code(error_conexion)
else:
    # --- MENSAJE DE BIENVENIDA EMPÁTICO ---
    if "mensajes" not in st.session_state or len(st.session_state.mensajes) == 0:
        st.session_state.mensajes = [{
            "role": "assistant", 
            "content": f"¡Hola! Soy PAUIa 🙋‍♀️. Estoy aquí para echarte una mano y que la PAU te parezca un paseo. \n\nHe cargado mis apuntes de **{asignatura}**. Dime, ¿qué dudas tienes hoy? ¡Vamos a por ese 10! 🚀"
        }]

    # --- HISTORIAL DE CHAT CON AVATARES NUEVOS ---
    for msg in st.session_state.mensajes:
        # El alumno es un emoji cool, PAUIa es la tutora levantando la mano
        icono = "✌️" if msg["role"] == "user" else "🙋‍♀️"
        with st.chat_message(msg["role"], avatar=icono):
            st.markdown(msg["content"])

    # --- CAJA DE TEXTO PRINCIPAL ---
    if prompt := st.chat_input("Escribe tu duda aquí (ej. ¿Cómo se calcula el rango?)..."):
        with st.chat_message("user", avatar="✌️"):
            st.markdown(prompt)
        st.session_state.mensajes.append({"role": "user", "content": prompt})

        with st.chat_message("assistant", avatar="🙋‍♀️"):
            with st.spinner("Revisando los apuntes... 📖"):
                try:
                    respuesta = chat_sesion.send_message(prompt)
                    try:
                        texto_final = respuesta.text
                    except Exception:
                        texto_final = "".join([part.text for part in respuesta.candidates[0].content.parts])
                    
                    st.markdown(texto_final)
                    st.session_state.mensajes.append({"role": "assistant", "content": texto_final})
                except Exception as e:
                    st.error(f"¡Vaya! Me he atascado buscando la respuesta: {e}")

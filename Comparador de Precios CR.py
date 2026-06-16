import streamlit as st
import pandas as pd
import hashlib
from supabase import create_client

st.set_page_config(page_title="Comparador de Precios CR", layout="wide", page_icon="🛒")

# --- CONEXIÓN A SUPABASE ---
try:
    # Cambia las variables a mayúsculas dentro de los corchetes
    client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
except Exception as e:
    st.error(f"❌ Error al conectar con Supabase: {e}")
    st.stop()


# ─────────────────────────────────────────────
# UTILIDADES DE AUTENTICACIÓN
# ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def registrar_usuario(email: str, password: str, nombre: str, apellido: str) -> tuple[bool, str]:
    try:
        existing = client.table("usuarios").select("id").eq("email", email).execute()
        if existing.data:
            return False, "Ya existe una cuenta con ese correo."

        client.table("usuarios").insert({
            "email":    email,
            "password": hash_password(password)
        }).execute()
        return True, "Cuenta creada exitosamente. Podés iniciar sesión."
    except Exception as e:
        return False, f"Error al registrar: {e}"


def iniciar_sesion(email: str, password: str) -> tuple[bool, str]:
    try:
        response = client.table("usuarios").select(
            "id, email, password, nombre, apellido"
        ).eq("email", email).execute()

        if not response.data:
            return False, "No existe una cuenta con ese correo."

        usuario = response.data[0]
        if usuario["password"] != hash_password(password):
            return False, "Contraseña incorrecta."

        st.session_state["autenticado"]      = True
        st.session_state["usuario_email"]    = usuario["email"]
        st.session_state["usuario_id"]       = usuario["id"]
        return True, "Sesión iniciada correctamente."
    except Exception as e:
        return False, f"Error al iniciar sesión: {e}"


def cerrar_sesion():
    for key in ["autenticado", "usuario_email", "usuario_id"]
        st.session_state[key] = None
    st.session_state["autenticado"] = False


# ─────────────────────────────────────────────
# INICIALIZAR SESSION STATE
# ─────────────────────────────────────────────

defaults = {
    "autenticado":      False,
    "usuario_email":    None,
    "usuario_id":       None
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ─────────────────────────────────────────────
# PANTALLA DE LOGIN / REGISTRO
# ─────────────────────────────────────────────

if not st.session_state["autenticado"]:
    st.title("🛒 Comparador Histórico de Precios CR")
    st.markdown("Ingresá a tu cuenta para acceder al comparador.")

    tab_login, tab_registro = st.tabs(["Iniciar Sesión", "Crear Cuenta"])

    with tab_login:
        with st.form("form_login"):
            email    = st.text_input("Correo electrónico", placeholder="tu@correo.com")
            password = st.text_input("Contraseña", type="password")
            submit   = st.form_submit_button("Ingresar", use_container_width=True)

        if submit:
            if not email or not password:
                st.warning("Completá todos los campos.")
            else:
                exito, mensaje = iniciar_sesion(email.strip().lower(), password)
                if exito:
                    st.success(mensaje)
                    st.rerun()
                else:
                    st.error(mensaje)

    with tab_registro:
        with st.form("form_registro"):
            col1, col2 = st.columns(2)
            with col1:
                nombre_reg = st.text_input("Nombre", placeholder="Juan", key="nombre_reg")
            with col2:
                apellido_reg = st.text_input("Apellido", placeholder="Pérez", key="apellido_reg")

            email_reg = st.text_input("Correo electrónico", placeholder="tu@correo.com", key="email_reg")
            pass_reg  = st.text_input("Contraseña", type="password", key="pass_reg")
            pass_conf = st.text_input("Confirmá la contraseña", type="password", key="pass_conf")
            submit_reg = st.form_submit_button("Crear cuenta", use_container_width=True)

        if submit_reg:
            if not nombre_reg or not apellido_reg or not email_reg or not pass_reg or not pass_conf:
                st.warning("Completá todos los campos.")
            elif pass_reg != pass_conf:
                st.error("Las contraseñas no coinciden.")
            elif len(pass_reg) < 6:
                st.warning("La contraseña debe tener al menos 6 caracteres.")
            else:
                exito, mensaje = registrar_usuario(
                    email_reg.strip().lower(), pass_reg,
                    nombre_reg.strip(), apellido_reg.strip()
                )
                if exito:
                    st.success(mensaje)
                else:
                    st.error(mensaje)

    st.stop()


# ─────────────────────────────────────────────
# APP PRINCIPAL (solo si está autenticado)
# ─────────────────────────────────────────────

st.title("🛒 Comparador Histórico de Precios CR")
st.markdown("Analizá la fluctuación de precios de la canasta básica en supermercados locales.")

with st.sidebar:
    nombre_completo = (
        f"{st.session_state['usuario_nombre']} {st.session_state['usuario_apellido']}"
    ).strip()
    st.markdown(f"👤 **{nombre_completo or st.session_state['usuario_email']}**")
    st.caption(st.session_state["usuario_email"])
    if st.button("Cerrar sesión", use_container_width=True):
        cerrar_sesion()
        st.rerun()
    st.divider()
    st.header("Filtros de Búsqueda")


# --- 1. CATEGORÍAS ---
@st.cache_data(ttl=600)
def obtener_categorias():
    try:
        response = client.table("categorias").select("id, nombre").order("nombre").execute()
        data = response.data
        return pd.DataFrame(data) if data else pd.DataFrame(columns=["id", "nombre"])
    except Exception as e:
        st.error(f"❌ Error cargando categorías: {e}")
        return pd.DataFrame(columns=["id", "nombre"])

df_cat = obtener_categorias()

if df_cat.empty:
    st.error("⚠️ No se pudieron cargar las categorías.")
    st.info("Revisá: 1) Los Secrets en Streamlit Cloud  2) RLS en Supabase  3) Que el proyecto no esté pausado.")
    st.stop()

# --- 2. SELECTOR DE CATEGORÍAS ---
categoria_sel  = st.sidebar.selectbox("1. Seleccioná una Categoría:", options=df_cat["nombre"])
id_cat_sel     = df_cat[df_cat["nombre"] == categoria_sel]["id"].values[0]


# --- 3. PRODUCTOS ---
@st.cache_data(ttl=300)
def obtener_productos(id_categoria):
    try:
        response = (
            client.table("productos")
            .select("id, nombre")
            .eq("categoria_id", int(id_categoria))
            .order("nombre")
            .execute()
        )
        data = response.data
        return pd.DataFrame(data) if data else pd.DataFrame(columns=["id", "nombre"])
    except Exception as e:
        st.error(f"❌ Error cargando productos: {e}")
        return pd.DataFrame(columns=["id", "nombre"])

df_prod = obtener_productos(id_cat_sel)

if not df_prod.empty:
    producto_sel = st.sidebar.selectbox("2. Seleccioná un Producto:", options=df_prod["nombre"])
    id_prod_sel  = df_prod[df_prod["nombre"] == producto_sel]["id"].values[0]

    # --- 4. HISTORIAL DE PRECIOS ---
    @st.cache_data(ttl=300)
    def obtener_historial(id_producto):
        try:
            response = (
                client.table("historial_precios")
                .select("supermercado, precio, fecha")
                .eq("producto_id", int(id_producto))
                .order("fecha")
                .execute()
            )
            data = response.data
            return pd.DataFrame(data) if data else pd.DataFrame(columns=["supermercado", "precio", "fecha"])
        except Exception as e:
            st.error(f"❌ Error cargando historial: {e}")
            return pd.DataFrame(columns=["supermercado", "precio", "fecha"])

    df_historial = obtener_historial(id_prod_sel)

    if df_historial.empty:
        st.info("No hay registros de precios para este producto todavía.")
    else:
        df_historial["fecha"] = pd.to_datetime(df_historial["fecha"])

        # --- MÉTRICAS DEL DÍA ---
        df_reciente = df_historial[df_historial["fecha"] == df_historial["fecha"].max()]
        if not df_reciente.empty:
            col1, col2 = st.columns(2)
            p_min = df_reciente["precio"].min()
            s_min = df_reciente[df_reciente["precio"] == p_min]["supermercado"].values[0]
            p_max = df_reciente["precio"].max()
            s_max = df_reciente[df_reciente["precio"] == p_max]["supermercado"].values[0]
            with col1:
                st.metric(label=f"Más barato hoy en {s_min}", value=f"₡{p_min:,.2f}")
            with col2:
                st.metric(label=f"Más caro hoy en {s_max}", value=f"₡{p_max:,.2f}")

        st.markdown("---")

        # --- GRÁFICO DE TENDENCIA ---
        st.subheader(f"📈 Tendencia Temporal: {producto_sel}")
        st.line_chart(
            data=df_historial,
            x="fecha",
            y="precio",
            color="supermercado",
            use_container_width=True
        )

        # --- TABLA DE HISTORIAL ---
        st.subheader("📋 Historial de Registros")
        st.dataframe(
            df_historial.style.format({"precio": "₡{:,}"}),
            use_container_width=True,
            hide_index=True
        )
else:
    st.info("No hay productos registrados en esta categoría.")

import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title="Comparador de Precios CR", layout="wide", page_icon="🛒")
st.title("🛒 Comparador Histórico de Precios CR")
st.markdown("Analizá la fluctuación de precios de la canasta básica en supermercados locales.")

# --- CONEXIÓN A SUPABASE ---
try:
    client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
except Exception as e:
    st.error(f"❌ Error al conectar con Supabase. Verificá los Secrets de la app: {e}")
    st.stop()

# --- 1. CATEGORÍAS ---
@st.cache_data(ttl=600)
def obtener_categorias():
    try:
        response = client.table("categorias").select("id, nombre").order("nombre").execute()
        data = response.data
        if not data:
            return pd.DataFrame(columns=["id", "nombre"])
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"❌ Error cargando categorías: {e}")
        return pd.DataFrame(columns=["id", "nombre"])

df_cat = obtener_categorias()

if df_cat.empty:
    st.error("⚠️ No se pudieron cargar las categorías. Verificá la conexión con Supabase.")
    st.info("Revisá: 1) Los Secrets en Streamlit Cloud  2) RLS en Supabase  3) Que el proyecto no esté pausado.")
    st.stop()

# --- 2. SELECTOR DE CATEGORÍAS (Barra Lateral) ---
st.sidebar.header("Filtros de Búsqueda")
categoria_sel = st.sidebar.selectbox("1. Seleccioná una Categoría:", options=df_cat["nombre"])
id_cat_sel = df_cat[df_cat["nombre"] == categoria_sel]["id"].values[0]

# --- 3. PRODUCTOS (Dependiente de la categoría) ---
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
        if not data:
            return pd.DataFrame(columns=["id", "nombre"])
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"❌ Error cargando productos: {e}")
        return pd.DataFrame(columns=["id", "nombre"])

df_prod = obtener_productos(id_cat_sel)

if not df_prod.empty:
    producto_sel = st.sidebar.selectbox("2. Seleccioná un Producto:", options=df_prod["nombre"])
    id_prod_sel = df_prod[df_prod["nombre"] == producto_sel]["id"].values[0]

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
            if not data:
                return pd.DataFrame(columns=["supermercado", "precio", "fecha"])
            return pd.DataFrame(data)
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

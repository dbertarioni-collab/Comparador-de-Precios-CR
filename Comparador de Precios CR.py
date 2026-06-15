import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title="Comparador de Precios CR", layout="wide", page_icon="🛒")

st.title("🛒 Comparador Histórico de Precios CR")
st.markdown("Analizá la fluctuación de precios de la canasta básica en supermercados locales.")

client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# 1. SELECTOR DE CATEGORÍAS (Barra Lateral)
@st.cache_data(ttl=600)
def obtener_categorias():
    data = client.table("categorias").select("id, nombre").order("nombre").execute().data
    return pd.DataFrame(data)

df_cat = obtener_categorias()

st.sidebar.header("Filtros de Búsqueda")
categoria_sel = st.sidebar.selectbox("1. Seleccioná una Categoría:", options=df_cat["nombre"])
id_cat_sel = df_cat[df_cat["nombre"] == categoria_sel]["id"].values[0]

# 2. SELECTOR DE PRODUCTOS (Dependiente de la categoría)
@st.cache_data(ttl=300)
def obtener_productos(id_categoria):
    data = (
        client.table("productos")
        .select("id, nombre")
        .eq("categoria_id", int(id_categoria))
        .order("nombre")
        .execute()
        .data
    )
    return pd.DataFrame(data)

df_prod = obtener_productos(id_cat_sel)

if not df_prod.empty:
    producto_sel = st.sidebar.selectbox("2. Seleccioná un Producto:", options=df_prod["nombre"])
    id_prod_sel = df_prod[df_prod["nombre"] == producto_sel]["id"].values[0]

    # 3. CONSULTA HISTÓRICA DEL PRODUCTO
    @st.cache_data(ttl=300)
    def obtener_historial(id_producto):
        data = (
            client.table("historial_precios")
            .select("supermercado, precio, fecha")
            .eq("producto_id", int(id_producto))
            .order("fecha")
            .execute()
            .data
        )
        return pd.DataFrame(data)

    df_historial = obtener_historial(id_prod_sel)
    df_historial["fecha"] = pd.to_datetime(df_historial["fecha"])

    # --- INTERFAZ PRINCIPAL ---
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

    st.subheader(f"📈 Tendencia Temporal: {producto_sel}")
    st.line_chart(data=df_historial, x="fecha", y="precio", color="supermercado", use_container_width=True)

    st.subheader("📋 Historial de Registros")
    st.dataframe(df_historial.style.format({"precio": "₡{:,}"}), use_container_width=True, hide_index=True)

else:
    st.info("No hay productos registrados en esta categoría.")

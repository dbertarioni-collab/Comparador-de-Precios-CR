import streamlit as st
import pandas as pd
import time
import random

# CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Comparador de Precios CR", page_icon="🛒", layout="wide")

st.title("🛒 Comparador de Precios de Supermercados - Costa Rica")
st.markdown("Prototipo analítico para comparar precios extraídos de e-commerce locales.")

# 1. FUNCIÓN DE EXTRACCIÓN (SIMULACIÓN DE SCRAPING)
# En un entorno real, aquí usarías BeautifulSoup, Selenium o Requests para raspar las webs.
@st.cache_data(ttl=3600) # Guarda los datos en caché por 1 hora para no saturar las fuentes
def extraer_datos_supermercados():
    # Simulamos un pequeño delay que toma el web scraping real
    time.sleep(1) 
    
    # Datos simulados basados en productos reales de cadenas en CR
    datos = [
        # --- Café ---
        {"producto": "Café Rey Tarrazú 500g", "supermercado": "Walmart", "precio": 3450, "categoria": "Abarrotes"},
        {"producto": "Café Rey Tarrazú 500g", "supermercado": "Auto Mercado", "precio": 3890, "categoria": "Abarrotes"},
        {"producto": "Café Rey Tarrazú 500g", "supermercado": "MasxMenos", "precio": 3450, "categoria": "Abarrotes"},
        
        # --- Leche ---
        {"producto": "Leche Semidescremada Dos Pinos 1L", "supermercado": "Walmart", "precio": 920, "categoria": "Lácteos"},
        {"producto": "Leche Semidescremada Dos Pinos 1L", "supermercado": "Auto Mercado", "precio": 980, "categoria": "Lácteos"},
        {"producto": "Leche Semidescremada Dos Pinos 1L", "supermercado": "MasxMenos", "precio": 925, "categoria": "Lácteos"},
        {"producto": "Leche Semidescremada Dos Pinos 1L", "supermercado": "MaxiPalí", "precio": 890, "categoria": "Lácteos"},
        
        # --- Arroz ---
        {"producto": "Arroz Tío Pelón 99% 1.8kg", "supermercado": "Walmart", "precio": 1620, "categoria": "Abarrotes"},
        {"producto": "Arroz Tío Pelón 99% 1.8kg", "supermercado": "Auto Mercado", "precio": 1750, "categoria": "Abarrotes"},
        {"producto": "Arroz Tío Pelón 99% 1.8kg", "supermercado": "MaxiPalí", "precio": 1590, "categoria": "Abarrotes"},
        
        # --- Aceite ---
        {"producto": "Aceite de Girasol Clover 1.5L", "supermercado": "Walmart", "precio": 2850, "categoria": "Abarrotes"},
        {"producto": "Aceite de Girasol Clover 1.5L", "supermercado": "Auto Mercado", "precio": 3100, "categoria": "Abarrotes"},
        {"producto": "Aceite de Girasol Clover 1.5L", "supermercado": "MasxMenos", "precio": 2850, "categoria": "Abarrotes"}
    ]
    return pd.DataFrame(datos)

# Cargar los datos
with st.spinner("Actualizando precios desde los e-commerce..."):
    df_precios = extraer_datos_supermercados()

# --- BARRA LATERAL (FILTROS) ---
st.sidebar.header("Filtros de Búsqueda")

# Filtro por Categoría
categorias = ["Todas"] + list(df_precios["categoria"].unique())
categoria_sel = st.sidebar.selectbox("Seleccioná una Categoría:", categorias)

# Filtro por Producto específico
if categoria_sel != "Todas":
    productos_filtrados = df_precios[df_precios["categoria"] == categoria_sel]["producto"].unique()
else:
    productos_filtrados = df_precios["producto"].unique()

producto_sel = st.sidebar.selectbox("Seleccioná un Producto para comparar:", productos_filtrados)

# --- CUERPO PRINCIPAL ---

# Filtrar el DataFrame según la selección del usuario
df_filtrado = df_precios[df_precios["producto"] == producto_sel].sort_values(by="precio")

# Métricas destacadas
if not df_filtrado.empty:
    col1, col2, col3 = st.columns(3)
    
    precio_min = df_filtrado["precio"].min()
    super_min = df_filtrado[df_filtrado["precio"] == precio_min]["supermercado"].values[0]
    
    precio_max = df_filtrado["precio"].max()
    super_max = df_filtrado[df_filtrado["precio"] == precio_max]["supermercado"].values[0]
    
    diferencia = precio_max - precio_min
    porcentaje_ahorro = (diferencia / precio_max) * 100

    with col1:
        st.metric(label=f"Precio Más Barato (en {super_min})", value=f"₡{precio_min:,.2f}")
    with col2:
        st.metric(label=f"Precio Más Caro (en {super_max})", value=f"₡{precio_max:,.2f}")
    with col3:
        st.metric(label="Ahorro Potencial Máximo", value=f"₡{diferencia:,.2f}", delta=f"-{porcentaje_ahorro:.1f}%")

st.markdown("---")

# Mostrar Tabla Comparativa e Histograma
col_tabla, col_grafico = st.columns([1, 1])

with col_tabla:
    st.subheader("📋 Lista Comparativa de Precios")
    # Formateamos la tabla para que se vea limpia
    st.dataframe(
        df_filtrado[["supermercado", "precio"]].style.format({"precio": "₡{:,}"}),
        use_container_width=True,
        hide_index=True
    )

with col_grafico:
    st.subheader("📊 Comparativa Visual")
    # Streamlit tiene gráficos nativos muy limpios basados en Altair
    st.bar_chart(
        data=df_filtrado,
        x="supermercado",
        y="precio",
        color="supermercado",
        use_container_width=True
    )

# --- NOTA TÉCNICA EXPLICATIVA ---
st.markdown("---")
with st.expander("🛠️ ¿Cómo funcionaría la recolección real detrás de este código?"):
    st.code("""
# Ejemplo conceptual de cómo reemplazar la función simulada con scraping real (Request a API oculta):
import requests

def scraping_real_walmart(codigo_barras):
    url = f"https://www.walmart.co.cr/api/v1/products/{codigo_barras}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data['price']
    return None
    """, language="python")

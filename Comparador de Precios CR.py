import streamlit as st
import anthropic
import sqlite3
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Precios CR",
    page_icon="🛒",
    layout="wide",
)

st.markdown("""
<style>
.super-badge {
    display: inline-block; font-size: 11px; padding: 2px 9px;
    border-radius: 999px; font-weight: 600; margin: 2px 3px;
}
.badge-walmart { background:#E6F1FB; color:#0C447C; }
.badge-auto    { background:#EAF3DE; color:#27500A; }
.badge-price   { background:#FAEEDA; color:#633806; }
.badge-maxi    { background:#FAECE7; color:#712B13; }
.badge-fresh   { background:#FBEAF0; color:#72243E; }
</style>
""", unsafe_allow_html=True)

# ── Base de datos SQLite ─────────────────────────────────────────────────────
DB_PATH = Path("precios_cr.db")

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre      TEXT NOT NULL,
                marca       TEXT,
                categoria   TEXT NOT NULL,
                supermercado TEXT NOT NULL,
                precio      REAL NOT NULL,
                unidad      TEXT,
                en_stock    INTEGER DEFAULT 1,
                notas       TEXT,
                extraido_en TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS extracciones (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                supermercado TEXT NOT NULL,
                categoria    TEXT NOT NULL,
                productos_n  INTEGER,
                realizado_en TEXT NOT NULL
            )
        """)
        conn.commit()

init_db()

def save_products(products: list, supermercado: str, categoria: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        for p in products:
            conn.execute("""
                INSERT INTO productos
                (nombre, marca, categoria, supermercado, precio, unidad, en_stock, notas, extraido_en)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                p.get("nombre", p.get("name", "")),
                p.get("marca", p.get("brand", "")),
                p.get("categoria", p.get("category", categoria)),
                p.get("supermercado", p.get("supermarket", supermercado)),
                float(p.get("precio", p.get("price", 0))),
                p.get("unidad", p.get("unit", "")),
                1 if p.get("en_stock", p.get("inStock", True)) else 0,
                p.get("notas", p.get("notes", "")),
                ts,
            ))
        conn.execute("""
            INSERT INTO extracciones (supermercado, categoria, productos_n, realizado_en)
            VALUES (?,?,?,?)
        """, (supermercado, categoria, len(products), ts))
        conn.commit()

def load_products(supermercado=None, categoria=None, search=None):
    query = "SELECT * FROM productos WHERE 1=1"
    params = []
    if supermercado and supermercado != "Todos":
        query += " AND supermercado = ?"
        params.append(supermercado)
    if categoria and categoria != "Todas":
        query += " AND categoria = ?"
        params.append(categoria)
    if search:
        query += " AND (nombre LIKE ? OR marca LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    query += " ORDER BY categoria, supermercado, precio"
    with get_conn() as conn:
        return pd.read_sql_query(query, conn, params=params)

def db_stats():
    with get_conn() as conn:
        total    = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        supers   = conn.execute("SELECT COUNT(DISTINCT supermercado) FROM productos").fetchone()[0]
        cats     = conn.execute("SELECT COUNT(DISTINCT categoria) FROM productos").fetchone()[0]
        last_ext = conn.execute("SELECT MAX(realizado_en) FROM extracciones").fetchone()[0]
    return total, supers, cats, last_ext

def get_categories():
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT categoria FROM productos ORDER BY categoria").fetchall()
    return ["Todas"] + [r[0] for r in rows]

def get_supermarkets_in_db():
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT supermercado FROM productos ORDER BY supermercado").fetchall()
    return ["Todos"] + [r[0] for r in rows]

def delete_all():
    with get_conn() as conn:
        conn.execute("DELETE FROM productos")
        conn.execute("DELETE FROM extracciones")
        conn.commit()

# ── Constantes ────────────────────────────────────────────────────────────────
SUPERMERCADOS = ["Walmart CR", "Automercado", "PriceSmart", "Maxi Palí", "Fresh Market"]
CATEGORIAS = [
    "Lácteos", "Granos y cereales", "Carnes", "Frutas y verduras",
    "Bebidas", "Limpieza", "Snacks", "Panadería", "Congelados",
    "Higiene personal", "Aceites y condimentos",
]

SYSTEM_EXTRACTOR = """Eres un extractor de precios de supermercados de Costa Rica.
Responde SOLO con JSON válido, sin texto extra, sin backticks, sin markdown.
Estructura exacta:
{
  "productos": [
    {
      "nombre": "nombre del producto",
      "marca": "marca",
      "categoria": "categoría exacta dada",
      "supermercado": "nombre exacto del supermercado",
      "precio": 1234,
      "unidad": "tamaño/presentación",
      "en_stock": true,
      "notas": "oferta o nota (opcional)"
    }
  ]
}
Precios en colones costarricenses (₡), valores realistas 2024-2025.
Marcas locales: Dos Pinos, Numar, Sabrostar, Palma Tica, Supremo, Buen Provecho, Coronado.
Genera entre 6 y 10 productos por solicitud. No repitas productos ya existentes si te los indico."""

SYSTEM_CHAT = """Eres un asistente experto en precios de supermercados de Costa Rica.
Responde en español, de forma conversacional, clara y útil.
Supermercados: Walmart CR, Automercado, PriceSmart, Maxi Palí, Fresh Market.
Precios en colones costarricenses (₡), valores realistas 2024-2025.
Marcas locales: Dos Pinos, Numar, Sabrostar, Palma Tica, Supremo, Buen Provecho.
Sé específico, da precios concretos, usá listas y tablas cuando ayude.
Si te dan datos de una base de datos, úsalos para responder con precisión."""

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuración")
    api_key = st.text_input("API Key de Anthropic", type="password", placeholder="sk-ant-...")
    st.divider()

    st.markdown("**Supermercados**")
    st.markdown("""
<span class="super-badge badge-walmart">Walmart CR</span>
<span class="super-badge badge-auto">Automercado</span>
<span class="super-badge badge-price">PriceSmart</span>
<span class="super-badge badge-maxi">Maxi Palí</span>
<span class="super-badge badge-fresh">Fresh Market</span>
""", unsafe_allow_html=True)

    st.divider()
    total, supers, cats, last_ext = db_stats()
    st.markdown("**Base de datos**")
    st.metric("Productos", total)
    col1, col2 = st.columns(2)
    col1.metric("Supers", supers)
    col2.metric("Categorías", cats)
    if last_ext:
        st.caption(f"Última extracción: {last_ext[:16]}")

    st.divider()
    if st.button("🗑️ Vaciar base de datos", use_container_width=True):
        delete_all()
        st.success("Base de datos vaciada.")
        st.rerun()

# ── Tabs principales ──────────────────────────────────────────────────────────
tab_chat, tab_extract, tab_db = st.tabs(["💬 Chat", "⬇️ Extraer datos", "🗄️ Base de datos"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 · CHAT
# ══════════════════════════════════════════════════════════════════════════════
with tab_chat:
    st.subheader("Consultá precios con IA")

    quick = {
        "🌾 Arroz":          "¿Cuánto cuesta el arroz en Walmart CR y Maxi Palí?",
        "🥛 Leche":          "Comparame precios de leche en todos los supermercados",
        "🍗 Pollo":          "¿Cuál supermercado tiene el pollo más barato?",
        "🛒 Mercado básico": "Dame una lista del mercado básico semanal con precios estimados",
        "🥦 Verduras":       "¿Dónde conviene más comprar frutas y verduras?",
        "📊 Más barato":     "¿Qué supermercado es generalmente el más barato en CR?",
    }

    cols = st.columns(3)
    for i, (label, prompt) in enumerate(quick.items()):
        if cols[i % 3].button(label, use_container_width=True, key=f"q_{i}"):
            st.session_state.quick_prompt = prompt

    st.divider()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🛒"):
            st.markdown(msg["content"])

    if not st.session_state.messages:
        with st.chat_message("assistant", avatar="🛒"):
            st.markdown("""¡Hola! Soy tu asistente de precios para supermercados en Costa Rica 🇨🇷

Podés preguntarme sobre precios, comparar supermercados o armar tu lista del mercado.
También podés ir a la pestaña **⬇️ Extraer datos** para poblar la base de datos con productos reales.""")

    if "quick_prompt" in st.session_state:
        user_input = st.session_state.pop("quick_prompt")
    else:
        user_input = st.chat_input("Preguntá sobre precios, productos o supermercados...")

    if user_input:
        if not api_key:
            st.error("⚠️ Ingresá tu API Key en el panel izquierdo.")
            st.stop()

        # Enriquecer con datos de la DB si hay
        context = ""
        if total > 0:
            df_ctx = load_products(search=user_input[:30])
            if not df_ctx.empty:
                sample = df_ctx.head(15).to_string(index=False)
                context = f"\n\nDatos reales de la base de datos (usalos si son relevantes):\n{sample}"

        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(user_input)

        client = anthropic.Anthropic(api_key=api_key)
        with st.chat_message("assistant", avatar="🛒"):
            placeholder = st.empty()
            full = ""
            try:
                with client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=SYSTEM_CHAT + context,
                    messages=[{"role": m["role"], "content": m["content"]}
                               for m in st.session_state.messages],
                ) as stream:
                    for chunk in stream.text_stream:
                        full += chunk
                        placeholder.markdown(full + "▌")
                placeholder.markdown(full)
            except anthropic.AuthenticationError:
                st.error("❌ API Key inválida.")
                st.stop()
            except Exception as e:
                st.error(f"❌ Error: {e}")
                st.stop()

        st.session_state.messages.append({"role": "assistant", "content": full})

    if st.session_state.get("messages"):
        if st.button("🗑️ Limpiar chat", key="clear_chat"):
            st.session_state.messages = []
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 · EXTRACCIÓN
# ══════════════════════════════════════════════════════════════════════════════
with tab_extract:
    st.subheader("⬇️ Extraer productos a la base de datos")
    st.caption("La IA generará precios estimados realistas para cada supermercado y categoría seleccionada.")

    col_a, col_b = st.columns(2)
    with col_a:
        sel_supers = st.multiselect("Supermercados", SUPERMERCADOS, default=SUPERMERCADOS)
    with col_b:
        sel_cats = st.multiselect("Categorías", CATEGORIAS, default=CATEGORIAS[:4])

    total_tasks = len(sel_supers) * len(sel_cats)
    st.info(f"Se realizarán **{total_tasks}** extracciones ({len(sel_supers)} supers × {len(sel_cats)} categorías)")

    if st.button("🚀 Iniciar extracción", type="primary", disabled=not api_key or not sel_supers or not sel_cats):
        if not api_key:
            st.error("⚠️ Ingresá tu API Key.")
            st.stop()

        client = anthropic.Anthropic(api_key=api_key)
        progress_bar = st.progress(0, text="Iniciando...")
        log = st.empty()
        done = 0
        errors = 0
        saved = 0
        logs = []

        for super_ in sel_supers:
            for cat in sel_cats:
                prompt = (
                    f"Extraé productos de la categoría '{cat}' del supermercado '{super_}' "
                    f"en Costa Rica. Generá entre 6 y 10 productos con precios realistas en colones. "
                    f"Incluí variedad de marcas y presentaciones."
                )
                try:
                    resp = client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=900,
                        system=SYSTEM_EXTRACTOR,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    raw = resp.content[0].text.strip().replace("```json","").replace("```","")
                    data = json.loads(raw)
                    products = data.get("productos", data.get("products", []))
                    save_products(products, super_, cat)
                    saved += len(products)
                    logs.append(f"✅ {super_} · {cat}: {len(products)} productos")
                except json.JSONDecodeError:
                    logs.append(f"⚠️ {super_} · {cat}: error al parsear JSON")
                    errors += 1
                except anthropic.AuthenticationError:
                    st.error("❌ API Key inválida.")
                    st.stop()
                except Exception as e:
                    logs.append(f"❌ {super_} · {cat}: {e}")
                    errors += 1

                done += 1
                pct = done / total_tasks
                progress_bar.progress(pct, text=f"{done}/{total_tasks} · {super_} · {cat}")
                log.markdown("\n".join(logs[-12:]))

        progress_bar.progress(1.0, text="✅ Extracción completa")
        st.success(f"Extracción finalizada: **{saved} productos** guardados, {errors} errores.")
        st.rerun()

    st.divider()
    st.markdown("**Extracción individual**")
    col1, col2, col3 = st.columns(3)
    with col1:
        one_super = st.selectbox("Supermercado", SUPERMERCADOS, key="one_super")
    with col2:
        one_cat = st.selectbox("Categoría", CATEGORIAS, key="one_cat")
    with col3:
        st.write("")
        st.write("")
        run_one = st.button("Extraer", key="run_one", disabled=not api_key)

    if run_one:
        if not api_key:
            st.error("⚠️ Ingresá tu API Key.")
            st.stop()
        client = anthropic.Anthropic(api_key=api_key)
        with st.spinner(f"Extrayendo {one_cat} de {one_super}..."):
            try:
                prompt = (
                    f"Extraé productos de la categoría '{one_cat}' del supermercado '{one_super}' "
                    f"en Costa Rica. Generá entre 6 y 10 productos con precios realistas en colones."
                )
                resp = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=900,
                    system=SYSTEM_EXTRACTOR,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = resp.content[0].text.strip().replace("```json","").replace("```","")
                data = json.loads(raw)
                products = data.get("productos", data.get("products", []))
                save_products(products, one_super, one_cat)
                st.success(f"✅ {len(products)} productos guardados en '{one_cat}' · {one_super}")
                st.dataframe(pd.DataFrame(products), use_container_width=True)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 · BASE DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_db:
    st.subheader("🗄️ Base de datos de productos")

    total, supers_n, cats_n, last_ext = db_stats()
    if total == 0:
        st.info("La base de datos está vacía. Andá a la pestaña **⬇️ Extraer datos** para poblarla.")
    else:
        # Métricas
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total productos", total)
        m2.metric("Supermercados", supers_n)
        m3.metric("Categorías", cats_n)
        m4.metric("Última actualización", last_ext[:10] if last_ext else "—")

        st.divider()

        # Filtros
        f1, f2, f3 = st.columns(3)
        with f1:
            f_super = st.selectbox("Supermercado", get_supermarkets_in_db(), key="f_super")
        with f2:
            f_cat = st.selectbox("Categoría", get_categories(), key="f_cat")
        with f3:
            f_search = st.text_input("Buscar producto", placeholder="Ej: leche, arroz...", key="f_search")

        df = load_products(
            supermercado=f_super if f_super != "Todos" else None,
            categoria=f_cat if f_cat != "Todas" else None,
            search=f_search if f_search else None,
        )

        st.caption(f"{len(df)} productos encontrados")

        if not df.empty:
            # Tabla principal
            display_cols = ["nombre", "marca", "categoria", "supermercado", "precio", "unidad", "en_stock", "notas"]
            df_show = df[display_cols].copy()
            df_show["precio"] = df_show["precio"].apply(lambda x: f"₡{x:,.0f}")
            df_show["en_stock"] = df_show["en_stock"].apply(lambda x: "✅" if x else "❌")
            df_show.columns = ["Nombre", "Marca", "Categoría", "Supermercado", "Precio", "Unidad", "Stock", "Notas"]
            st.dataframe(df_show, use_container_width=True, height=380)

            st.divider()

            # Análisis por categoría
            st.markdown("**Precio promedio por categoría**")
            pivot = df.groupby("categoria")["precio"].agg(["mean","min","max","count"]).round(0).reset_index()
            pivot.columns = ["Categoría", "Promedio (₡)", "Mínimo (₡)", "Máximo (₡)", "Productos"]
            st.dataframe(pivot, use_container_width=True, hide_index=True)

            st.divider()

            # Comparador de precios por supermercado
            st.markdown("**Precio promedio por supermercado**")
            pivot2 = df.groupby("supermercado")["precio"].agg(["mean","count"]).round(0).reset_index()
            pivot2.columns = ["Supermercado", "Precio promedio (₡)", "Productos"]
            pivot2 = pivot2.sort_values("Precio promedio (₡)")
            st.dataframe(pivot2, use_container_width=True, hide_index=True)

            st.divider()

            # Exportar
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Exportar CSV",
                data=csv,
                file_name=f"precios_cr_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )

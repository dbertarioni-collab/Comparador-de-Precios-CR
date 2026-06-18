import streamlit as st
import anthropic
import sqlite3
import json
import pandas as pd
import re
from datetime import datetime
from pathlib import Path

# ── Página ───────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Precios CR", page_icon="🛒", layout="wide")

st.markdown("""
<style>
.super-badge { display:inline-block; font-size:11px; padding:2px 9px;
  border-radius:999px; font-weight:600; margin:2px 3px; }
.badge-walmart { background:#E6F1FB; color:#0C447C; }
.badge-auto    { background:#EAF3DE; color:#27500A; }
.badge-price   { background:#FAEEDA; color:#633806; }
.badge-maxi    { background:#FAECE7; color:#712B13; }
.badge-fresh   { background:#FBEAF0; color:#72243E; }
.step-box { background:#f8f8f6; border:0.5px solid #ddd; border-radius:10px;
  padding:14px 18px; margin-bottom:12px; }
.step-num { font-size:22px; font-weight:600; color:#378ADD; margin-right:8px; }
</style>
""", unsafe_allow_html=True)

# ── SQLite ────────────────────────────────────────────────────────────────────
DB_PATH = Path("precios_cr.db")

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre        TEXT NOT NULL,
                marca         TEXT,
                categoria     TEXT NOT NULL,
                supermercado  TEXT NOT NULL,
                precio        REAL NOT NULL,
                unidad        TEXT,
                en_stock      INTEGER DEFAULT 1,
                notas         TEXT,
                url_fuente    TEXT,
                extraido_en   TEXT NOT NULL
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS extracciones (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                supermercado  TEXT NOT NULL,
                categoria     TEXT NOT NULL,
                metodo        TEXT NOT NULL,
                productos_n   INTEGER,
                realizado_en  TEXT NOT NULL
            )""")
        conn.commit()

init_db()

def save_products(products, supermercado, categoria, metodo="ia", url=""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        for p in products:
            conn.execute("""
                INSERT INTO productos
                (nombre,marca,categoria,supermercado,precio,unidad,en_stock,notas,url_fuente,extraido_en)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                p.get("nombre", p.get("name", "")),
                p.get("marca",  p.get("brand", "")),
                p.get("categoria", p.get("category", categoria)),
                p.get("supermercado", p.get("supermarket", supermercado)),
                float(p.get("precio", p.get("price", 0))),
                p.get("unidad", p.get("unit", "")),
                1 if p.get("en_stock", p.get("inStock", True)) else 0,
                p.get("notas",  p.get("notes", "")),
                url, ts,
            ))
        conn.execute("""
            INSERT INTO extracciones (supermercado,categoria,metodo,productos_n,realizado_en)
            VALUES (?,?,?,?,?)""", (supermercado, categoria, metodo, len(products), ts))
        conn.commit()

def load_products(supermercado=None, categoria=None, search=None):
    q = "SELECT * FROM productos WHERE 1=1"
    params = []
    if supermercado and supermercado != "Todos":
        q += " AND supermercado=?"; params.append(supermercado)
    if categoria and categoria != "Todas":
        q += " AND categoria=?";    params.append(categoria)
    if search:
        q += " AND (nombre LIKE ? OR marca LIKE ?)"; params += [f"%{search}%"]*2
    q += " ORDER BY categoria, supermercado, precio"
    with get_conn() as conn:
        return pd.read_sql_query(q, conn, params=params)

def db_stats():
    with get_conn() as conn:
        total  = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        supers = conn.execute("SELECT COUNT(DISTINCT supermercado) FROM productos").fetchone()[0]
        cats   = conn.execute("SELECT COUNT(DISTINCT categoria) FROM productos").fetchone()[0]
        last   = conn.execute("SELECT MAX(realizado_en) FROM extracciones").fetchone()[0]
    return total, supers, cats, last

def get_distinct(col, table="productos"):
    with get_conn() as conn:
        rows = conn.execute(f"SELECT DISTINCT {col} FROM {table} ORDER BY {col}").fetchall()
    return [r[0] for r in rows]

def delete_all():
    with get_conn() as conn:
        conn.execute("DELETE FROM productos")
        conn.execute("DELETE FROM extracciones")
        conn.commit()

# ── Constantes ────────────────────────────────────────────────────────────────
SUPERMERCADOS = ["Walmart CR","Automercado","PriceSmart","Maxi Palí","Fresh Market"]
CATEGORIAS = [
    "Lácteos","Granos y cereales","Carnes","Frutas y verduras",
    "Bebidas","Limpieza","Snacks","Panadería","Congelados",
    "Higiene personal","Aceites y condimentos",
]
URLS_SUPERS = {
    "Walmart CR":   "https://www.walmart.co.cr/supermercado",
    "Automercado":  "https://www.automercado.co.cr",
    "PriceSmart":   "https://www.pricesmart.com/es/cr",
    "Maxi Palí":    "https://www.maxipali.co.cr",
    "Fresh Market": "https://www.freshmarket.co.cr",
}

SYSTEM_SCRAPER = """Eres un extractor experto de datos de supermercados de Costa Rica.
Recibirás HTML crudo de una página de supermercado. Tu tarea es identificar y extraer TODOS los productos visibles con sus precios.
Responde SOLO con JSON válido, sin texto extra, sin backticks.
Estructura exacta:
{
  "supermercado": "nombre detectado o indicado",
  "url": "url de la página si aparece",
  "productos": [
    {
      "nombre": "nombre completo del producto",
      "marca": "marca si está disponible",
      "categoria": "categoría inferida",
      "precio": 1234,
      "precio_rebajado": 999,
      "unidad": "tamaño/presentación",
      "en_stock": true,
      "notas": "oferta, descuento u observación"
    }
  ]
}
- Extrae el precio numérico en colones (₡), sin símbolos ni comas.
- Si hay precio normal y precio rebajado, incluí ambos.
- Si el HTML no contiene productos claros, devolvé {"productos": [], "error": "descripción del problema"}.
- Inferí la categoría basándote en el nombre del producto."""

SYSTEM_EXTRACTOR_IA = """Eres un extractor de precios de supermercados de Costa Rica.
Responde SOLO con JSON válido, sin texto extra, sin backticks.
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
      "notas": ""
    }
  ]
}
Precios en colones costarricenses (₡), valores realistas 2024-2025.
Marcas: Dos Pinos, Numar, Sabrostar, Palma Tica, Supremo, Buen Provecho, Coronado.
Generá entre 6 y 10 productos."""

SYSTEM_CHAT = """Eres un asistente experto en precios de supermercados de Costa Rica.
Responde en español, conversacional y útil.
Supermercados: Walmart CR, Automercado, PriceSmart, Maxi Palí, Fresh Market.
Precios en colones (₡), valores realistas 2024-2025.
Si te dan datos de base de datos, úsalos para responder con precisión."""

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuración")
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "") if hasattr(st, "secrets") else ""
    if not api_key:
        api_key = st.text_input("API Key de Anthropic", type="password", placeholder="sk-ant-...")
    else:
        st.success("🔑 API Key cargada desde secrets")

    st.divider()
    st.markdown("**Supermercados**")
    st.markdown("""
<span class="super-badge badge-walmart">Walmart CR</span>
<span class="super-badge badge-auto">Automercado</span>
<span class="super-badge badge-price">PriceSmart</span>
<span class="super-badge badge-maxi">Maxi Palí</span>
<span class="super-badge badge-fresh">Fresh Market</span>""", unsafe_allow_html=True)

    st.divider()
    total, supers_n, cats_n, last_ext = db_stats()
    st.markdown("**Base de datos**")
    st.metric("Productos guardados", total)
    c1, c2 = st.columns(2)
    c1.metric("Supers", supers_n)
    c2.metric("Categorías", cats_n)
    if last_ext:
        st.caption(f"Última extracción:\n{last_ext[:16]}")
    st.divider()
    if st.button("🗑️ Vaciar base de datos", use_container_width=True):
        delete_all()
        st.success("Base de datos vaciada.")
        st.rerun()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_chat, tab_scrape, tab_ia, tab_db = st.tabs([
    "💬 Chat",
    "🌐 Scraper semi-manual",
    "🤖 Extracción con IA",
    "🗄️ Base de datos",
])

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

Podés preguntarme sobre precios o ir a **🌐 Scraper semi-manual** para extraer datos reales de las páginas web.""")

    user_input = st.session_state.pop("quick_prompt", None) or st.chat_input("Preguntá sobre precios...")

    if user_input:
        if not api_key:
            st.error("⚠️ Ingresá tu API Key en el panel izquierdo.")
            st.stop()

        context = ""
        if total > 0:
            df_ctx = load_products(search=user_input[:40])
            if not df_ctx.empty:
                context = f"\n\nDatos reales de la base de datos:\n{df_ctx.head(20).to_string(index=False)}"

        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(user_input)

        client = anthropic.Anthropic(api_key=api_key)
        with st.chat_message("assistant", avatar="🛒"):
            ph = st.empty()
            full = ""
            try:
                with client.messages.stream(
                    model="claude-sonnet-4-6", max_tokens=1024,
                    system=SYSTEM_CHAT + context,
                    messages=[{"role": m["role"], "content": m["content"]}
                               for m in st.session_state.messages],
                ) as stream:
                    for chunk in stream.text_stream:
                        full += chunk
                        ph.markdown(full + "▌")
                ph.markdown(full)
            except Exception as e:
                st.error(f"❌ Error: {e}")
                st.stop()

        st.session_state.messages.append({"role": "assistant", "content": full})

    if st.session_state.get("messages"):
        if st.button("🗑️ Limpiar chat", key="clear_chat"):
            st.session_state.messages = []
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 · SCRAPER SEMI-MANUAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_scrape:
    st.subheader("🌐 Scraper semi-manual — datos reales")
    st.caption("Copiás el HTML de la página del supermercado y la IA extrae los productos automáticamente.")

    # Instrucciones paso a paso
    st.markdown("""
<div class="step-box">
<span class="step-num">1</span><strong>Abrí la página del supermercado</strong><br>
Hacé clic en el enlace del super que querés y buscá la sección de productos o categoría.
</div>
<div class="step-box">
<span class="step-num">2</span><strong>Copiá el HTML de la página</strong><br>
En el navegador: <code>clic derecho → Ver código fuente de la página</code> → Ctrl+A → Ctrl+C<br>
<em>O también: abrí DevTools (F12) → pestaña Elements → copiá el &lt;body&gt;</em>
</div>
<div class="step-box">
<span class="step-num">3</span><strong>Pegá el HTML abajo y hacé clic en Extraer</strong>
</div>
""", unsafe_allow_html=True)

    # Links a los supers
    st.markdown("**Abrí el supermercado que querés:**")
    link_cols = st.columns(5)
    for i, (super_, url) in enumerate(URLS_SUPERS.items()):
        link_cols[i].link_button(super_, url, use_container_width=True)

    st.divider()

    # Formulario de extracción
    col_left, col_right = st.columns([2, 1])

    with col_right:
        sc_super = st.selectbox("Supermercado", SUPERMERCADOS, key="sc_super")
        sc_cat   = st.selectbox("Categoría (si no se detecta automáticamente)",
                                 CATEGORIAS, key="sc_cat")
        sc_url   = st.text_input("URL de la página (opcional)",
                                  placeholder="https://www.walmart.co.cr/...", key="sc_url")
        st.markdown("**Consejos:**")
        st.markdown("""
- Buscá una categoría específica (ej: lácteos, carnes)
- Evitá páginas con captcha
- El HTML puede ser grande — pegá solo la sección de productos si querés
- Automercado y Fresh Market suelen funcionar mejor
""")

    with col_left:
        html_input = st.text_area(
            "Pegá el HTML de la página aquí",
            height=280,
            placeholder="<!DOCTYPE html><html>...",
            key="html_input",
        )

        char_count = len(html_input)
        if char_count > 0:
            st.caption(f"{char_count:,} caracteres pegados — "
                       f"{'✅ listo para procesar' if char_count > 500 else '⚠️ parece muy poco HTML'}")

        extract_btn = st.button(
            "🔍 Extraer productos con IA",
            type="primary",
            disabled=not html_input or not api_key,
            key="extract_btn",
        )

    if extract_btn:
        if not api_key:
            st.error("⚠️ Ingresá tu API Key.")
            st.stop()
        if len(html_input) < 200:
            st.warning("El HTML parece muy corto. ¿Copiaste bien la página?")
            st.stop()

        # Limpiamos el HTML para reducir tokens (quitamos scripts, styles, comentarios)
        html_clean = re.sub(r'<script[^>]*>.*?</script>', '', html_input, flags=re.DOTALL)
        html_clean = re.sub(r'<style[^>]*>.*?</style>',  '', html_clean, flags=re.DOTALL)
        html_clean = re.sub(r'<!--.*?-->',                '', html_clean, flags=re.DOTALL)
        html_clean = re.sub(r'\s+',                       ' ', html_clean)
        # Truncar a ~80k caracteres para no exceder contexto
        html_clean = html_clean[:80000]

        prompt = f"""Supermercado indicado: {sc_super}
Categoría sugerida: {sc_cat}
URL: {sc_url or 'no proporcionada'}

HTML de la página:
{html_clean}"""

        client = anthropic.Anthropic(api_key=api_key)

        with st.spinner("🤖 La IA está analizando el HTML y extrayendo productos..."):
            try:
                resp = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=2000,
                    system=SYSTEM_SCRAPER,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw  = resp.content[0].text.strip().replace("```json","").replace("```","")
                data = json.loads(raw)
            except json.JSONDecodeError:
                st.error("❌ La IA no devolvió JSON válido. Intentá con menos HTML o una sección más específica.")
                st.code(resp.content[0].text[:500])
                st.stop()
            except Exception as e:
                st.error(f"❌ Error: {e}")
                st.stop()

        products = data.get("productos", data.get("products", []))

        if data.get("error"):
            st.warning(f"⚠️ La IA reportó: {data['error']}")

        if not products:
            st.warning("No se encontraron productos en el HTML. Probá con otra sección de la página o una categoría específica.")
        else:
            st.success(f"✅ Se encontraron **{len(products)} productos**")

            df_preview = pd.DataFrame(products)
            # Mostrar preview editable
            st.markdown("**Vista previa — podés editar antes de guardar:**")
            df_edited = st.data_editor(
                df_preview,
                use_container_width=True,
                num_rows="dynamic",
                key="df_edited",
            )

            col_save, col_discard = st.columns([1, 3])
            if col_save.button("💾 Guardar en base de datos", type="primary"):
                records = df_edited.to_dict("records")
                save_products(records, sc_super, sc_cat, metodo="scraper", url=sc_url)
                st.success(f"✅ {len(records)} productos guardados en la base de datos.")
                st.rerun()
            col_discard.caption("Revisá los datos antes de guardar. Podés editar celdas directamente en la tabla.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 · EXTRACCIÓN CON IA
# ══════════════════════════════════════════════════════════════════════════════
with tab_ia:
    st.subheader("🤖 Extracción con IA (precios estimados)")
    st.caption("Útil para rellenar categorías o supermercados que no pudiste scrapear.")

    col_a, col_b = st.columns(2)
    with col_a:
        sel_supers = st.multiselect("Supermercados", SUPERMERCADOS, default=["Walmart CR", "Maxi Palí"])
    with col_b:
        sel_cats = st.multiselect("Categorías", CATEGORIAS, default=CATEGORIAS[:3])

    total_tasks = len(sel_supers) * len(sel_cats)
    if total_tasks:
        st.info(f"Se realizarán **{total_tasks}** extracciones ({len(sel_supers)} supers × {len(sel_cats)} categorías)")

    if st.button("🚀 Iniciar extracción", type="primary",
                  disabled=not api_key or not sel_supers or not sel_cats):
        client  = anthropic.Anthropic(api_key=api_key)
        bar     = st.progress(0, text="Iniciando...")
        log_box = st.empty()
        done = errors = saved = 0
        logs = []

        for super_ in sel_supers:
            for cat in sel_cats:
                try:
                    resp = client.messages.create(
                        model="claude-sonnet-4-6", max_tokens=900,
                        system=SYSTEM_EXTRACTOR_IA,
                        messages=[{"role": "user", "content":
                            f"Extraé productos de '{cat}' en '{super_}' CR. "
                            f"Precios realistas en colones, 6-10 productos."}],
                    )
                    raw  = resp.content[0].text.strip().replace("```json","").replace("```","")
                    data = json.loads(raw)
                    prods = data.get("productos", data.get("products", []))
                    save_products(prods, super_, cat, metodo="ia")
                    saved += len(prods)
                    logs.append(f"✅ {super_} · {cat}: {len(prods)} productos")
                except Exception as e:
                    logs.append(f"❌ {super_} · {cat}: {e}")
                    errors += 1

                done += 1
                bar.progress(done / total_tasks, text=f"{done}/{total_tasks} · {super_} · {cat}")
                log_box.markdown("\n".join(logs[-10:]))

        bar.progress(1.0, text="✅ Completo")
        st.success(f"**{saved} productos** guardados, {errors} errores.")
        st.rerun()

    st.divider()
    st.markdown("**Extracción individual**")
    c1, c2, c3 = st.columns(3)
    one_super = c1.selectbox("Supermercado", SUPERMERCADOS, key="one_s")
    one_cat   = c2.selectbox("Categoría",    CATEGORIAS,    key="one_c")
    c3.write(""); c3.write("")
    if c3.button("Extraer", disabled=not api_key):
        client = anthropic.Anthropic(api_key=api_key)
        with st.spinner(f"Extrayendo {one_cat} de {one_super}..."):
            try:
                resp = client.messages.create(
                    model="claude-sonnet-4-6", max_tokens=900,
                    system=SYSTEM_EXTRACTOR_IA,
                    messages=[{"role": "user", "content":
                        f"Extraé productos de '{one_cat}' en '{one_super}' CR. "
                        f"Precios realistas en colones, 6-10 productos."}],
                )
                raw   = resp.content[0].text.strip().replace("```json","").replace("```","")
                prods = json.loads(raw).get("productos", [])
                save_products(prods, one_super, one_cat, metodo="ia")
                st.success(f"✅ {len(prods)} productos guardados")
                st.dataframe(pd.DataFrame(prods), use_container_width=True)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 · BASE DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_db:
    st.subheader("🗄️ Base de datos de productos")

    total, supers_n, cats_n, last_ext = db_stats()
    if total == 0:
        st.info("La base de datos está vacía. Usá **🌐 Scraper semi-manual** o **🤖 Extracción con IA** para poblarla.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total productos", total)
        m2.metric("Supermercados",   supers_n)
        m3.metric("Categorías",      cats_n)
        m4.metric("Última actualización", last_ext[:10] if last_ext else "—")

        st.divider()

        f1, f2, f3 = st.columns(3)
        f_super  = f1.selectbox("Supermercado", ["Todos"] + get_distinct("supermercado"))
        f_cat    = f2.selectbox("Categoría",    ["Todas"] + get_distinct("categoria"))
        f_search = f3.text_input("Buscar", placeholder="Ej: leche, arroz...")

        df = load_products(
            supermercado=f_super  if f_super  != "Todos"  else None,
            categoria   =f_cat    if f_cat    != "Todas"  else None,
            search      =f_search if f_search else None,
        )

        st.caption(f"{len(df)} productos encontrados")

        if not df.empty:
            disp = df[["nombre","marca","categoria","supermercado","precio","unidad","en_stock","notas","url_fuente","extraido_en"]].copy()
            disp["precio"]   = disp["precio"].apply(lambda x: f"₡{x:,.0f}")
            disp["en_stock"] = disp["en_stock"].apply(lambda x: "✅" if x else "❌")
            disp.columns     = ["Nombre","Marca","Categoría","Supermercado","Precio",
                                 "Unidad","Stock","Notas","Fuente","Extraído"]
            st.dataframe(disp, use_container_width=True, height=360)

            st.divider()
            ca, cb = st.columns(2)

            with ca:
                st.markdown("**Precio promedio por categoría**")
                piv1 = df.groupby("categoria")["precio"].agg(["mean","min","max","count"]).round(0).reset_index()
                piv1.columns = ["Categoría","Promedio ₡","Mín ₡","Máx ₡","Productos"]
                st.dataframe(piv1, use_container_width=True, hide_index=True)

            with cb:
                st.markdown("**Precio promedio por supermercado**")
                piv2 = df.groupby("supermercado")["precio"].agg(["mean","count"]).round(0).reset_index()
                piv2.columns = ["Supermercado","Promedio ₡","Productos"]
                piv2 = piv2.sort_values("Promedio ₡")
                st.dataframe(piv2, use_container_width=True, hide_index=True)

            st.divider()
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Exportar CSV completo",
                data=csv,
                file_name=f"precios_cr_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )

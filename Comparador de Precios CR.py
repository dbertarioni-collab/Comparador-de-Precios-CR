import streamlit as st
import anthropic
import sqlite3
import json
import pandas as pd
import re
import requests
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

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
.url-card { background:#f8f8f6; border:0.5px solid #ddd; border-radius:10px;
  padding:14px 18px; margin-bottom:10px; }
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
                precio_rebajado REAL,
                unidad        TEXT,
                en_stock      INTEGER DEFAULT 1,
                notas         TEXT,
                url_fuente    TEXT,
                metodo        TEXT,
                extraido_en   TEXT NOT NULL
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS extracciones (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                supermercado  TEXT,
                url           TEXT,
                metodo        TEXT,
                productos_n   INTEGER,
                realizado_en  TEXT NOT NULL
            )""")
        conn.commit()

init_db()

def save_products(products, supermercado, categoria, metodo="url", url=""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    saved = 0
    with get_conn() as conn:
        for p in products:
            precio = p.get("precio", p.get("price", 0))
            try:
                precio = float(str(precio).replace(",","").replace("₡","").replace(" ",""))
            except:
                precio = 0
            if precio <= 0:
                continue
            conn.execute("""
                INSERT INTO productos
                (nombre,marca,categoria,supermercado,precio,precio_rebajado,
                 unidad,en_stock,notas,url_fuente,metodo,extraido_en)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                p.get("nombre", p.get("name", ""))[:200],
                p.get("marca",  p.get("brand", "")),
                p.get("categoria", p.get("category", categoria)),
                p.get("supermercado", p.get("supermarket", supermercado)),
                precio,
                p.get("precio_rebajado") or None,
                p.get("unidad", p.get("unit", "")),
                1 if p.get("en_stock", p.get("inStock", True)) else 0,
                p.get("notas", p.get("notes", "")),
                url, metodo, ts,
            ))
            saved += 1
        conn.execute("""
            INSERT INTO extracciones (supermercado,url,metodo,productos_n,realizado_en)
            VALUES (?,?,?,?,?)""", (supermercado, url, metodo, saved, ts))
        conn.commit()
    return saved

def load_products(supermercado=None, categoria=None, search=None):
    q = "SELECT * FROM productos WHERE 1=1"
    params = []
    if supermercado and supermercado != "Todos":
        q += " AND supermercado=?"; params.append(supermercado)
    if categoria and categoria != "Todas":
        q += " AND categoria=?"; params.append(categoria)
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

def get_distinct(col):
    with get_conn() as conn:
        rows = conn.execute(f"SELECT DISTINCT {col} FROM productos ORDER BY {col}").fetchall()
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

# URLs de categorías conocidas para extracción directa
URLS_CATEGORIAS = {
    "Automercado": {
        "Lácteos":           "https://www.automercado.co.cr/lacteos",
        "Carnes":            "https://www.automercado.co.cr/carnes",
        "Frutas y verduras": "https://www.automercado.co.cr/frutas-y-verduras",
        "Bebidas":           "https://www.automercado.co.cr/bebidas",
        "Panadería":         "https://www.automercado.co.cr/panaderia",
    },
    "Fresh Market": {
        "Lácteos":           "https://www.freshmarket.co.cr/lacteos",
        "Bebidas":           "https://www.freshmarket.co.cr/bebidas",
    },
    "Maxi Palí": {
        "Lácteos":           "https://www.maxipali.co.cr/lacteos",
        "Granos y cereales": "https://www.maxipali.co.cr/granos-y-cereales",
        "Bebidas":           "https://www.maxipali.co.cr/bebidas",
    },
    "Walmart CR": {
        "Lácteos":           "https://www.walmart.co.cr/supermercado/lacteos",
        "Bebidas":           "https://www.walmart.co.cr/supermercado/bebidas",
        "Limpieza":          "https://www.walmart.co.cr/supermercado/limpieza",
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SYSTEM_SCRAPER = """Eres un extractor experto de precios de supermercados de Costa Rica.
Recibirás texto extraído del HTML de una página de supermercado.
Responde SOLO con JSON válido, sin texto extra, sin backticks.
Estructura:
{
  "productos": [
    {
      "nombre": "nombre completo del producto",
      "marca": "marca si está disponible",
      "categoria": "categoría inferida",
      "supermercado": "nombre del supermercado",
      "precio": 1234,
      "precio_rebajado": null,
      "unidad": "tamaño/presentación",
      "en_stock": true,
      "notas": "oferta o descuento si aplica"
    }
  ],
  "total_encontrados": 10,
  "error": null
}
- Extrae el precio numérico en colones, solo el número sin símbolos.
- Si hay precio tachado y precio rebajado, incluí ambos.
- Si no encontrás productos claros devolvé {"productos": [], "error": "razón"}.
- Inferí la categoría desde el nombre del producto."""

SYSTEM_CHAT = """Eres un asistente experto en precios de supermercados de Costa Rica.
Responde en español, conversacional y útil.
Supermercados: Walmart CR, Automercado, PriceSmart, Maxi Palí, Fresh Market.
Precios en colones costarricenses (₡).
Si te dan datos de la base de datos úsalos para responder con precisión."""

SYSTEM_IA = """Eres un extractor de precios de supermercados de Costa Rica.
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
Precios en colones costarricenses, valores realistas 2024-2025.
Marcas: Dos Pinos, Numar, Sabrostar, Palma Tica, Supremo, Buen Provecho, Coronado.
Generá entre 6 y 10 productos."""

# ── Fetch de URL ──────────────────────────────────────────────────────────────
def fetch_url(url: str) -> tuple[str, str]:
    """Descarga una URL y devuelve (texto_limpio, error)"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Quitar scripts, styles, nav, footer
        for tag in soup(["script","style","nav","footer","header","noscript","svg","iframe"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text)
        # Limitar a 60k caracteres
        return text[:60000], None

    except requests.exceptions.Timeout:
        return "", "La página tardó demasiado en responder (timeout)."
    except requests.exceptions.HTTPError as e:
        return "", f"Error HTTP {e.response.status_code} — la página bloqueó el acceso."
    except requests.exceptions.ConnectionError:
        return "", "No se pudo conectar a la página. Verificá el URL."
    except Exception as e:
        return "", str(e)

def detectar_supermercado(url: str) -> str:
    url_l = url.lower()
    if "walmart"      in url_l: return "Walmart CR"
    if "automercado"  in url_l: return "Automercado"
    if "pricesmart"   in url_l: return "PriceSmart"
    if "maxipali"     in url_l: return "Maxi Palí"
    if "freshmarket"  in url_l: return "Fresh Market"
    return "Desconocido"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuración")
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "") if hasattr(st, "secrets") else ""
    if not api_key:
        api_key = st.text_input("API Key de Anthropic", type="password", placeholder="sk-ant-...")
    else:
        st.success("🔑 API Key cargada")

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
tab_url, tab_chat, tab_ia, tab_db = st.tabs([
    "🔗 Extraer por URL",
    "💬 Chat",
    "🤖 Extracción con IA",
    "🗄️ Base de datos",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 · EXTRAER POR URL
# ══════════════════════════════════════════════════════════════════════════════
with tab_url:
    st.subheader("🔗 Extraer productos desde una URL")
    st.caption("Pegá el link de cualquier página de productos y la app extrae los precios automáticamente.")

    # URLs sugeridas por supermercado
    with st.expander("📋 URLs sugeridas por supermercado (hacé clic para copiar)", expanded=True):
        for super_, cats in URLS_CATEGORIAS.items():
            st.markdown(f"**{super_}**")
            for cat, url in cats.items():
                st.code(url, language=None)

    st.divider()

    # Extracción de una URL
    col_url, col_cat = st.columns([3, 1])
    with col_url:
        url_input = st.text_input(
            "URL de la página de productos",
            placeholder="https://www.automercado.co.cr/lacteos",
            key="url_input",
        )
    with col_cat:
        cat_override = st.selectbox("Categoría (opcional)", ["Detectar automáticamente"] + CATEGORIAS)

    if url_input:
        super_detectado = detectar_supermercado(url_input)
        st.caption(f"Supermercado detectado: **{super_detectado}**")

    extract_url_btn = st.button(
        "🚀 Extraer productos",
        type="primary",
        disabled=not url_input or not api_key,
        key="extract_url_btn",
    )

    if extract_url_btn:
        if not api_key:
            st.error("⚠️ Ingresá tu API Key.")
            st.stop()

        super_ = detectar_supermercado(url_input)
        cat    = cat_override if cat_override != "Detectar automáticamente" else "General"

        with st.status(f"Extrayendo productos de {super_}...", expanded=True) as status:
            st.write(f"📡 Descargando página: `{url_input}`")
            texto, error = fetch_url(url_input)

            if error:
                status.update(label="❌ Error al descargar", state="error")
                st.error(f"**No se pudo descargar la página:** {error}")
                st.info("""**¿Qué podés hacer?**
- Verificá que el URL sea correcto y accesible en tu navegador
- Algunos supers (Walmart CR, PriceSmart) bloquean bots — probá con Automercado o Fresh Market
- Usá la pestaña 🤖 Extracción con IA para obtener precios estimados""")
                st.stop()

            if len(texto) < 300:
                status.update(label="⚠️ Página con poco contenido", state="error")
                st.warning("La página descargada tiene muy poco texto. Puede requerir JavaScript para cargar (sitio dinámico).")
                st.info("Probá con Automercado o Fresh Market que tienen mejor compatibilidad.")
                st.stop()

            st.write(f"✅ Página descargada ({len(texto):,} caracteres)")
            st.write("🤖 Analizando con IA...")

            client = anthropic.Anthropic(api_key=api_key)
            try:
                resp = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=2000,
                    system=SYSTEM_SCRAPER,
                    messages=[{"role": "user", "content":
                        f"Supermercado: {super_}\nCategoría sugerida: {cat}\nURL: {url_input}\n\nTexto de la página:\n{texto}"
                    }],
                )
                raw  = resp.content[0].text.strip().replace("```json","").replace("```","")
                data = json.loads(raw)
            except json.JSONDecodeError:
                status.update(label="❌ Error al procesar", state="error")
                st.error("La IA no pudo procesar el contenido de esta página.")
                st.stop()
            except Exception as e:
                status.update(label="❌ Error", state="error")
                st.error(f"Error: {e}")
                st.stop()

            products = data.get("productos", [])
            err_ia   = data.get("error")

            if err_ia:
                st.warning(f"⚠️ La IA reportó: {err_ia}")

            if not products:
                status.update(label="⚠️ Sin productos encontrados", state="error")
                st.warning("No se encontraron productos en esta página. Probá con una URL de categoría específica.")
                st.stop()

            status.update(label=f"✅ {len(products)} productos encontrados", state="complete")

        st.success(f"✅ Se extrajeron **{len(products)} productos** de {super_}")

        df_prev = pd.DataFrame(products)
        st.markdown("**Vista previa — podés editar antes de guardar:**")
        df_edit = st.data_editor(df_prev, use_container_width=True, num_rows="dynamic", key="df_edit_url")

        col_save, col_info = st.columns([1, 3])
        if col_save.button("💾 Guardar en base de datos", type="primary", key="save_url"):
            records = df_edit.to_dict("records")
            n = save_products(records, super_, cat, metodo="url", url=url_input)
            st.success(f"✅ {n} productos guardados.")
            st.rerun()
        col_info.caption("Podés editar celdas directamente antes de guardar.")

    st.divider()

    # Extracción masiva con URLs conocidas
    st.markdown("### ⚡ Extracción masiva con URLs conocidas")
    st.caption("Extrae automáticamente todas las URLs que tenemos guardadas.")

    all_urls = [(s, c, u) for s, cats in URLS_CATEGORIAS.items() for c, u in cats.items()]
    st.info(f"Tenemos **{len(all_urls)} URLs** de categorías conocidas listas para extraer.")

    sel_supers_bulk = st.multiselect(
        "Filtrar por supermercado",
        list(URLS_CATEGORIAS.keys()),
        default=list(URLS_CATEGORIAS.keys()),
    )
    urls_filtradas = [(s, c, u) for s, c, u in all_urls if s in sel_supers_bulk]

    if st.button("🚀 Extraer todas", type="primary",
                  disabled=not api_key or not urls_filtradas, key="bulk_btn"):
        client  = anthropic.Anthropic(api_key=api_key)
        bar     = st.progress(0)
        log_box = st.empty()
        logs    = []
        total_saved = 0

        for i, (super_, cat, url) in enumerate(urls_filtradas):
            texto, error = fetch_url(url)
            if error or len(texto) < 300:
                logs.append(f"⚠️ {super_} · {cat}: {error or 'página vacía'}")
                bar.progress((i+1)/len(urls_filtradas))
                log_box.markdown("\n".join(logs[-8:]))
                continue

            try:
                resp = client.messages.create(
                    model="claude-sonnet-4-6", max_tokens=2000,
                    system=SYSTEM_SCRAPER,
                    messages=[{"role": "user", "content":
                        f"Supermercado: {super_}\nCategoría: {cat}\nURL: {url}\n\nTexto:\n{texto[:50000]}"
                    }],
                )
                raw  = resp.content[0].text.strip().replace("```json","").replace("```","")
                data = json.loads(raw)
                prods = data.get("productos", [])
                n = save_products(prods, super_, cat, metodo="url", url=url)
                total_saved += n
                logs.append(f"✅ {super_} · {cat}: {n} productos")
            except Exception as e:
                logs.append(f"❌ {super_} · {cat}: {e}")

            bar.progress((i+1)/len(urls_filtradas))
            log_box.markdown("\n".join(logs[-8:]))

        st.success(f"✅ Extracción completa: **{total_saved} productos** guardados.")
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 · CHAT
# ══════════════════════════════════════════════════════════════════════════════
with tab_chat:
    st.subheader("💬 Consultá precios con IA")

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
            st.markdown("¡Hola! Soy tu asistente de precios 🇨🇷 Preguntame lo que quieras sobre productos y supermercados.")

    user_input = st.session_state.pop("quick_prompt", None) or st.chat_input("Preguntá sobre precios...")

    if user_input:
        if not api_key:
            st.error("⚠️ Ingresá tu API Key.")
            st.stop()

        context = ""
        total_db, _, _, _ = db_stats()
        if total_db > 0:
            df_ctx = load_products(search=user_input[:40])
            if not df_ctx.empty:
                context = f"\n\nDatos reales de la base de datos:\n{df_ctx.head(20).to_string(index=False)}"

        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(user_input)

        client = anthropic.Anthropic(api_key=api_key)
        with st.chat_message("assistant", avatar="🛒"):
            ph = st.empty(); full = ""
            try:
                with client.messages.stream(
                    model="claude-sonnet-4-6", max_tokens=1024,
                    system=SYSTEM_CHAT + context,
                    messages=[{"role": m["role"], "content": m["content"]}
                               for m in st.session_state.messages],
                ) as stream:
                    for chunk in stream.text_stream:
                        full += chunk; ph.markdown(full + "▌")
                ph.markdown(full)
            except Exception as e:
                st.error(f"❌ {e}"); st.stop()

        st.session_state.messages.append({"role": "assistant", "content": full})

    if st.session_state.get("messages"):
        if st.button("🗑️ Limpiar chat"):
            st.session_state.messages = []; st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 · EXTRACCIÓN CON IA
# ══════════════════════════════════════════════════════════════════════════════
with tab_ia:
    st.subheader("🤖 Extracción con IA — precios estimados")
    st.caption("Para supers que bloquean el acceso directo (Walmart CR, PriceSmart). Los precios son estimados realistas.")

    col_a, col_b = st.columns(2)
    sel_supers = col_a.multiselect("Supermercados", SUPERMERCADOS, default=["Walmart CR","PriceSmart"])
    sel_cats   = col_b.multiselect("Categorías",    CATEGORIAS,    default=CATEGORIAS[:3])

    total_tasks = len(sel_supers) * len(sel_cats)
    if total_tasks:
        st.info(f"**{total_tasks}** extracciones ({len(sel_supers)} supers × {len(sel_cats)} categorías)")

    if st.button("🚀 Iniciar", type="primary",
                  disabled=not api_key or not sel_supers or not sel_cats):
        client = anthropic.Anthropic(api_key=api_key)
        bar = st.progress(0); log_box = st.empty()
        done = errors = saved = 0; logs = []

        for super_ in sel_supers:
            for cat in sel_cats:
                try:
                    resp = client.messages.create(
                        model="claude-sonnet-4-6", max_tokens=900,
                        system=SYSTEM_IA,
                        messages=[{"role": "user", "content":
                            f"Extraé productos de '{cat}' en '{super_}' CR. "
                            f"Precios realistas en colones, 6-10 productos."}],
                    )
                    raw   = resp.content[0].text.strip().replace("```json","").replace("```","")
                    prods = json.loads(raw).get("productos", [])
                    n = save_products(prods, super_, cat, metodo="ia")
                    saved += n; logs.append(f"✅ {super_} · {cat}: {n} productos")
                except Exception as e:
                    logs.append(f"❌ {super_} · {cat}: {e}"); errors += 1
                done += 1
                bar.progress(done/total_tasks)
                log_box.markdown("\n".join(logs[-10:]))

        st.success(f"✅ **{saved} productos** guardados, {errors} errores.")
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 · BASE DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_db:
    st.subheader("🗄️ Base de datos de productos")
    total, supers_n, cats_n, last_ext = db_stats()

    if total == 0:
        st.info("La base de datos está vacía. Usá **🔗 Extraer por URL** para poblarla con datos reales.")
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
        f_search = f3.text_input("Buscar producto", placeholder="Ej: leche, arroz...")

        df = load_products(
            supermercado=f_super  if f_super  != "Todos" else None,
            categoria   =f_cat    if f_cat    != "Todas" else None,
            search      =f_search or None,
        )
        st.caption(f"{len(df)} productos encontrados")

        if not df.empty:
            cols_show = ["nombre","marca","categoria","supermercado","precio","precio_rebajado","unidad","en_stock","metodo","extraido_en"]
            disp = df[[c for c in cols_show if c in df.columns]].copy()
            disp["precio"] = disp["precio"].apply(lambda x: f"₡{x:,.0f}")
            if "precio_rebajado" in disp.columns:
                disp["precio_rebajado"] = disp["precio_rebajado"].apply(
                    lambda x: f"₡{x:,.0f}" if pd.notna(x) and x else "—")
            if "en_stock" in disp.columns:
                disp["en_stock"] = disp["en_stock"].apply(lambda x: "✅" if x else "❌")
            st.dataframe(disp, use_container_width=True, height=360)

            st.divider()
            ca, cb = st.columns(2)
            with ca:
                st.markdown("**Promedio por categoría**")
                piv1 = df.groupby("categoria")["precio"].agg(["mean","min","max","count"]).round(0).reset_index()
                piv1.columns = ["Categoría","Promedio ₡","Mín ₡","Máx ₡","Prods"]
                st.dataframe(piv1, use_container_width=True, hide_index=True)
            with cb:
                st.markdown("**Promedio por supermercado**")
                piv2 = df.groupby("supermercado")["precio"].agg(["mean","count"]).round(0).reset_index()
                piv2.columns = ["Supermercado","Promedio ₡","Prods"]
                piv2 = piv2.sort_values("Promedio ₡")
                st.dataframe(piv2, use_container_width=True, hide_index=True)

            st.divider()
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Exportar CSV",
                data=csv,
                file_name=f"precios_cr_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )

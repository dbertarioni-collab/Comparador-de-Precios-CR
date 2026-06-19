import streamlit as st
import anthropic
import sqlite3
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

# ── Página ────────────────────────────────────────────────────────────────────
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
</style>
""", unsafe_allow_html=True)

# ── API Key — un solo lugar ───────────────────────────────────────────────────
def get_api_key():
    """Lee la API key desde secrets o desde session_state."""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return st.session_state.get("api_key", "")

# ── SQLite ────────────────────────────────────────────────────────────────────
DB_PATH = Path("precios_cr.db")

def get_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS productos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre          TEXT NOT NULL,
                marca           TEXT,
                categoria       TEXT NOT NULL,
                supermercado    TEXT NOT NULL,
                precio          REAL NOT NULL,
                precio_rebajado REAL,
                unidad          TEXT,
                en_stock        INTEGER DEFAULT 1,
                notas           TEXT,
                fuente          TEXT,
                extraido_en     TEXT NOT NULL
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS errores (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                supermercado  TEXT,
                categoria     TEXT,
                etapa         TEXT,
                mensaje       TEXT,
                detalle       TEXT,
                registrado_en TEXT NOT NULL
            )""")
        conn.commit()

init_db()

def save_error(supermercado, categoria, etapa, mensaje, detalle=""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_conn() as conn:
            conn.execute("""INSERT INTO errores
                (supermercado,categoria,etapa,mensaje,detalle,registrado_en)
                VALUES (?,?,?,?,?,?)""",
                (supermercado, categoria, etapa, str(mensaje)[:500], str(detalle)[:1000], ts))
            conn.commit()
    except Exception:
        pass

def save_products(products, supermercado, categoria, fuente="web_search"):
    if not products:
        save_error(supermercado, categoria, "save", "Lista vacía")
        return 0
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    saved = 0
    with get_conn() as conn:
        for p in products:
            try:
                precio_raw = p.get("precio", p.get("price", 0))
                precio = float(str(precio_raw).replace(",","").replace("₡","").replace(" ","").strip() or 0)
                nombre = str(p.get("nombre", p.get("name",""))).strip()[:200]
                if precio <= 0 or not nombre:
                    save_error(supermercado, categoria, "precio_invalido",
                               f"precio={precio_raw} nombre={nombre}")
                    continue
                conn.execute("""INSERT INTO productos
                    (nombre,marca,categoria,supermercado,precio,precio_rebajado,
                     unidad,en_stock,notas,fuente,extraido_en)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                    nombre,
                    p.get("marca", p.get("brand","")),
                    p.get("categoria", p.get("category", categoria)),
                    p.get("supermercado", p.get("supermarket", supermercado)),
                    precio,
                    p.get("precio_rebajado") or None,
                    p.get("unidad", p.get("unit","")),
                    1 if p.get("en_stock", True) else 0,
                    p.get("notas", p.get("notes","")),
                    fuente, ts,
                ))
                saved += 1
            except Exception as e:
                save_error(supermercado, categoria, "insert", str(e), str(p)[:300])
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
        last   = conn.execute("SELECT MAX(extraido_en) FROM productos").fetchone()[0]
        n_err  = conn.execute("SELECT COUNT(*) FROM errores").fetchone()[0]
    return total, supers, cats, last, n_err

def get_distinct(col):
    with get_conn() as conn:
        return [r[0] for r in conn.execute(
            f"SELECT DISTINCT {col} FROM productos WHERE {col} IS NOT NULL ORDER BY {col}").fetchall()]

def delete_all():
    with get_conn() as conn:
        conn.execute("DELETE FROM productos")
        conn.execute("DELETE FROM errores")
        conn.commit()

# ── Constantes ────────────────────────────────────────────────────────────────
SUPERMERCADOS = ["Walmart CR","Automercado","PriceSmart","Maxi Palí","Fresh Market"]
CATEGORIAS = [
    "Lácteos","Granos y cereales","Carnes","Frutas y verduras",
    "Bebidas","Limpieza","Snacks","Panadería","Congelados",
    "Higiene personal","Aceites y condimentos",
]

SYSTEM_EXTRACTOR = """Eres un extractor de precios de supermercados de Costa Rica.
Usá la herramienta de búsqueda web para encontrar precios REALES y actuales.
Buscá en los sitios oficiales: walmart.co.cr, automercado.co.cr, maxipali.co.cr, freshmarket.co.cr, pricesmart.com/cr

Después de buscar, responde SOLO con JSON válido sin backticks:
{
  "productos": [
    {
      "nombre": "nombre completo",
      "marca": "marca",
      "categoria": "categoría",
      "supermercado": "nombre exacto",
      "precio": 1234,
      "precio_rebajado": null,
      "unidad": "presentación/tamaño",
      "en_stock": true,
      "notas": "oferta u observación"
    }
  ]
}
- Precio en colones costarricenses, solo número sin símbolos.
- Si no encontrás precios reales, indicalo con {"productos":[],"error":"no encontrado"}.
- No inventes precios. Solo reportá lo que encontraste en la web."""

SYSTEM_CHAT = """Eres un asistente experto en precios de supermercados de Costa Rica.
Tenés acceso a búsqueda web — usala para encontrar precios actuales cuando te lo pidan.
Responde en español, de forma conversacional y útil.
Supermercados: Walmart CR, Automercado, PriceSmart, Maxi Palí, Fresh Market.
Precios en colones costarricenses (₡).
Si te dan datos de la base de datos, priorizalos en tu respuesta."""

# ── Función de extracción con web search ─────────────────────────────────────
def extraer_con_web_search(api_key, supermercado, categoria, status_placeholder=None):
    """Usa la API de Anthropic con web_search para obtener precios reales."""
    sitios = {
        "Walmart CR":   "walmart.co.cr",
        "Automercado":  "automercado.co.cr",
        "PriceSmart":   "pricesmart.com/cr",
        "Maxi Palí":    "maxipali.co.cr",
        "Fresh Market": "freshmarket.co.cr",
    }
    sitio = sitios.get(supermercado, supermercado.lower().replace(" ",""))

    prompt = (
        f"Buscá precios actuales de productos de la categoría '{categoria}' "
        f"en {supermercado} Costa Rica. "
        f"Buscá en el sitio {sitio} o en búsquedas recientes de precios CR. "
        f"Extraé al menos 6 productos con sus precios reales en colones. "
        f"Devolvé solo el JSON."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=SYSTEM_EXTRACTOR,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        # Extraer el texto final (puede haber tool_use blocks)
        full_text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                full_text += block.text

        if not full_text.strip():
            save_error(supermercado, categoria, "respuesta_vacia", "Sin texto en respuesta")
            return []

        clean = full_text.strip().replace("```json","").replace("```","").strip()
        # Buscar el JSON en el texto
        start = clean.find("{")
        end   = clean.rfind("}") + 1
        if start == -1 or end == 0:
            save_error(supermercado, categoria, "json_no_encontrado", clean[:300])
            return []

        data  = json.loads(clean[start:end])
        prods = data.get("productos", [])
        err   = data.get("error")

        if err:
            save_error(supermercado, categoria, "web_search_error", err)

        return prods

    except json.JSONDecodeError as e:
        save_error(supermercado, categoria, "json_parse", str(e), full_text[:300])
        return []
    except anthropic.AuthenticationError:
        save_error(supermercado, categoria, "auth_error", "API Key inválida")
        raise
    except Exception as e:
        save_error(supermercado, categoria, "extraccion", str(e))
        return []

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuración")

    # API Key management
    stored_key = get_api_key()
    if stored_key:
        st.success(f"🔑 API Key: `{stored_key[:12]}...`")
        if st.button("Cambiar API Key"):
            st.session_state.api_key = ""
            st.rerun()
    else:
        key_input = st.text_input("API Key de Anthropic", type="password",
                                   placeholder="sk-ant-...")
        if st.button("Guardar key", type="primary"):
            if key_input.startswith("sk-"):
                st.session_state.api_key = key_input
                st.success("✅ API Key guardada")
                st.rerun()
            else:
                st.error("La key debe empezar con sk-ant-...")

    st.divider()
    st.markdown("**Supermercados**")
    st.markdown("""
<span class="super-badge badge-walmart">Walmart CR</span>
<span class="super-badge badge-auto">Automercado</span>
<span class="super-badge badge-price">PriceSmart</span>
<span class="super-badge badge-maxi">Maxi Palí</span>
<span class="super-badge badge-fresh">Fresh Market</span>""", unsafe_allow_html=True)

    st.divider()
    total, supers_n, cats_n, last_ext, n_err = db_stats()
    st.markdown("**Base de datos**")
    st.metric("Productos", total)
    c1, c2 = st.columns(2)
    c1.metric("Supers", supers_n)
    c2.metric("Categorías", cats_n)
    if last_ext:
        st.caption(f"Última extracción:\n{last_ext[:16]}")
    if n_err > 0:
        st.warning(f"⚠️ {n_err} errores registrados")
    st.divider()
    if st.button("🗑️ Vaciar todo", use_container_width=True):
        delete_all()
        st.success("Base de datos vaciada.")
        st.rerun()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_extract, tab_chat, tab_db, tab_err = st.tabs([
    "⬇️ Extraer precios",
    "💬 Chat",
    "🗄️ Base de datos",
    "⚠️ Errores",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 · EXTRAER PRECIOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_extract:
    st.subheader("⬇️ Extraer precios reales con búsqueda web")
    st.caption("La IA busca en los sitios oficiales de los supermercados y extrae precios actuales automáticamente.")

    api_key = get_api_key()

    if not api_key:
        st.warning("⚠️ Primero ingresá tu API Key en el panel izquierdo.")
        st.stop()

    # ── Extraer todo ─────────────────────────────────────────────────────────
    st.markdown("### 🚀 Extraer todo de una vez")

    col_s, col_c = st.columns(2)
    sel_supers = col_s.multiselect("Supermercados", SUPERMERCADOS,
                                    default=SUPERMERCADOS, key="sel_s")
    sel_cats   = col_c.multiselect("Categorías", CATEGORIAS,
                                    default=CATEGORIAS[:4], key="sel_c")

    total_comb = len(sel_supers) * len(sel_cats)
    if total_comb:
        st.info(f"**{total_comb} combinaciones** · ~{total_comb * 7} productos estimados")

    if st.button(f"🚀 Extraer todo ({total_comb} búsquedas)", type="primary", key="btn_all"):
        if not sel_supers or not sel_cats:
            st.error("Seleccioná al menos un supermercado y una categoría.")
            st.stop()

        tasks = [(s, c) for s in sel_supers for c in sel_cats]
        bar      = st.progress(0, text="Iniciando...")
        col_l, col_r = st.columns([2,1])
        log_box  = col_l.empty()
        stat_box = col_r.empty()
        logs     = []
        n_ok = n_err_count = n_saved = 0

        for i, (super_, cat) in enumerate(tasks):
            bar.progress((i+1)/len(tasks), text=f"{i+1}/{len(tasks)} · {super_} · {cat}")
            try:
                prods = extraer_con_web_search(api_key, super_, cat)
                n = save_products(prods, super_, cat, fuente="web_search")
                n_saved += n
                n_ok    += 1
                logs.append(f"✅ {super_} · {cat}: {n} productos")
            except anthropic.AuthenticationError:
                st.error("❌ API Key inválida. Corregila en el panel izquierdo.")
                st.stop()
            except Exception as e:
                save_error(super_, cat, "loop", str(e))
                logs.append(f"❌ {super_} · {cat}: {e}")
                n_err_count += 1

            log_box.markdown("\n".join(logs[-14:]))
            stat_box.markdown(f"""
**Progreso**
- ✅ OK: {n_ok}
- ❌ Errores: {n_err_count}
- 💾 Guardados: **{n_saved}**
""")

        bar.progress(1.0, text="✅ Completo")
        st.success(f"🎉 **{n_saved} productos** guardados. {n_err_count} errores.")
        st.rerun()

    st.divider()

    # ── Extracción individual ─────────────────────────────────────────────────
    st.markdown("### 🔍 Buscar un producto específico")
    st.caption("Buscá precios de cualquier producto en todos los supermercados.")

    col1, col2, col3 = st.columns([2,1,1])
    producto_buscar = col1.text_input("Producto", placeholder="Ej: leche Dos Pinos, arroz Tío Pelón...")
    super_buscar    = col2.selectbox("Supermercado", ["Todos"] + SUPERMERCADOS, key="sb_super")
    cat_buscar      = col3.selectbox("Categoría",    ["Auto"]  + CATEGORIAS,    key="sb_cat")

    if st.button("🔍 Buscar precio", type="primary", key="btn_one"):
        if not producto_buscar:
            st.error("Escribí un producto para buscar.")
            st.stop()

        supers_a_buscar = SUPERMERCADOS if super_buscar == "Todos" else [super_buscar]
        cat = cat_buscar if cat_buscar != "Auto" else "General"

        todos_prods = []
        bar2 = st.progress(0)
        status_txt = st.empty()

        for i, s in enumerate(supers_a_buscar):
            status_txt.caption(f"Buscando en {s}...")
            bar2.progress((i+1)/len(supers_a_buscar))
            try:
                client = anthropic.Anthropic(api_key=api_key)
                resp = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1000,
                    system=SYSTEM_EXTRACTOR,
                    tools=[{"type": "web_search_20250305", "name": "web_search"}],
                    messages=[{"role": "user", "content":
                        f"Buscá el precio actual de '{producto_buscar}' en {s} Costa Rica. "
                        f"Devolvé el JSON con los resultados."}],
                )
                full_text = "".join(b.text for b in resp.content if hasattr(b, "text"))
                clean = full_text.strip().replace("```json","").replace("```","").strip()
                start = clean.find("{"); end = clean.rfind("}") + 1
                if start >= 0 and end > 0:
                    prods = json.loads(clean[start:end]).get("productos", [])
                    n = save_products(prods, s, cat, fuente="busqueda_manual")
                    todos_prods.extend(prods)
            except Exception as e:
                save_error(s, cat, "busqueda_individual", str(e))

        status_txt.empty()
        bar2.empty()

        if todos_prods:
            st.success(f"✅ {len(todos_prods)} resultados encontrados")
            df = pd.DataFrame(todos_prods)
            if "precio" in df.columns:
                df["precio"] = df["precio"].apply(lambda x: f"₡{float(str(x).replace(',','') or 0):,.0f}")
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("No se encontraron resultados. Probá con otro nombre o categoría.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 · CHAT
# ══════════════════════════════════════════════════════════════════════════════
with tab_chat:
    st.subheader("💬 Consultá precios con IA + búsqueda web")

    api_key = get_api_key()

    quick = {
        "🌾 Arroz":          "¿Cuánto cuesta el arroz en Walmart CR y Maxi Palí ahora mismo?",
        "🥛 Leche":          "Buscá precios de leche Dos Pinos en todos los supermercados de CR",
        "🍗 Pollo":          "¿Cuál supermercado tiene el pollo más barato esta semana?",
        "🛒 Mercado básico": "Buscá precios actuales del mercado básico semanal en Costa Rica",
        "🥦 Verduras":       "¿Dónde conviene más comprar frutas y verduras en CR hoy?",
        "📊 Comparar":       "Comparame precios del aceite de cocina en todos los supermercados de CR",
    }
    cols = st.columns(3)
    for i, (label, prompt) in enumerate(quick.items()):
        if cols[i%3].button(label, use_container_width=True, key=f"q_{i}"):
            st.session_state.quick_prompt = prompt

    st.divider()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🛒"):
            st.markdown(msg["content"])

    if not st.session_state.messages:
        with st.chat_message("assistant", avatar="🛒"):
            st.markdown("""¡Hola! 🇨🇷 Puedo buscar precios **en tiempo real** en los supermercados de Costa Rica.

Preguntame sobre cualquier producto y voy a buscar en la web para darte precios actuales.""")

    user_input = st.session_state.pop("quick_prompt", None) or st.chat_input("Preguntá sobre precios...")

    if user_input:
        if not api_key:
            st.error("⚠️ Ingresá tu API Key en el panel izquierdo.")
            st.stop()

        context = ""
        total_db = db_stats()[0]
        if total_db > 0:
            df_ctx = load_products(search=user_input[:40])
            if not df_ctx.empty:
                context = f"\n\nDatos en base de datos local:\n{df_ctx.head(15).to_string(index=False)}"

        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(user_input)

        client = anthropic.Anthropic(api_key=api_key)
        with st.chat_message("assistant", avatar="🛒"):
            ph = st.empty()
            full = ""
            try:
                with client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=SYSTEM_CHAT + context,
                    tools=[{"type": "web_search_20250305", "name": "web_search"}],
                    messages=[{"role": m["role"], "content": m["content"]}
                               for m in st.session_state.messages],
                ) as stream:
                    for chunk in stream.text_stream:
                        full += chunk
                        ph.markdown(full + "▌")
                ph.markdown(full)
            except Exception as e:
                st.error(f"❌ {e}")
                save_error("chat","—","stream", str(e))
                st.stop()

        st.session_state.messages.append({"role": "assistant", "content": full})

    if st.session_state.get("messages"):
        if st.button("🗑️ Limpiar chat", key="clear_chat"):
            st.session_state.messages = []
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 · BASE DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_db:
    st.subheader("🗄️ Base de datos de productos")
    total, supers_n, cats_n, last_ext, _ = db_stats()

    if total == 0:
        st.info("La base de datos está vacía. Usá **⬇️ Extraer precios** para poblarla.")
    else:
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Total productos", total)
        m2.metric("Supermercados",   supers_n)
        m3.metric("Categorías",      cats_n)
        m4.metric("Actualizado",     last_ext[:10] if last_ext else "—")

        st.divider()
        f1,f2,f3 = st.columns(3)
        f_super  = f1.selectbox("Supermercado", ["Todos"] + get_distinct("supermercado"))
        f_cat    = f2.selectbox("Categoría",    ["Todas"] + get_distinct("categoria"))
        f_search = f3.text_input("Buscar", placeholder="Ej: leche, arroz...")

        df = load_products(
            supermercado=f_super  if f_super  != "Todos" else None,
            categoria   =f_cat    if f_cat    != "Todas" else None,
            search      =f_search or None,
        )
        st.caption(f"{len(df)} productos")

        if not df.empty:
            cols_show = ["nombre","marca","categoria","supermercado","precio","unidad","en_stock","extraido_en"]
            disp = df[[c for c in cols_show if c in df.columns]].copy()
            disp["precio"]   = disp["precio"].apply(lambda x: f"₡{x:,.0f}")
            disp["en_stock"] = disp["en_stock"].apply(lambda x: "✅" if x else "❌")
            st.dataframe(disp, use_container_width=True, height=380)

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
                st.dataframe(piv2.sort_values("Promedio ₡"), use_container_width=True, hide_index=True)

            st.divider()
            st.download_button("⬇️ Exportar CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"precios_cr_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 · ERRORES
# ══════════════════════════════════════════════════════════════════════════════
with tab_err:
    st.subheader("⚠️ Registro de errores")
    with get_conn() as conn:
        df_err = pd.read_sql_query("SELECT * FROM errores ORDER BY registrado_en DESC", conn)

    if df_err.empty:
        st.success("✅ No hay errores registrados.")
    else:
        st.error(f"**{len(df_err)} errores** registrados.")

        resumen = df_err.groupby("etapa").size().reset_index(name="cantidad").sort_values("cantidad", ascending=False)
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        st.divider()

        fe1, fe2 = st.columns(2)
        f_s = fe1.selectbox("Supermercado", ["Todos"] + sorted(df_err["supermercado"].dropna().unique().tolist()), key="err_s")
        f_e = fe2.selectbox("Etapa",        ["Todas"] + sorted(df_err["etapa"].dropna().unique().tolist()),        key="err_e")

        df_show = df_err.copy()
        if f_s != "Todos": df_show = df_show[df_show["supermercado"] == f_s]
        if f_e != "Todas": df_show = df_show[df_show["etapa"] == f_e]

        st.dataframe(df_show[["registrado_en","supermercado","categoria","etapa","mensaje","detalle"]],
                     use_container_width=True, height=350)

        col_dl, col_cl = st.columns([1,3])
        col_dl.download_button("⬇️ Exportar errores",
            data=df_err.to_csv(index=False).encode("utf-8"),
            file_name="errores_cr.csv", mime="text/csv")
        if col_cl.button("🗑️ Limpiar errores", key="clear_err"):
            with get_conn() as conn:
                conn.execute("DELETE FROM errores"); conn.commit()
            st.rerun()

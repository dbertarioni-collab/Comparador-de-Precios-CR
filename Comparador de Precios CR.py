import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path

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
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre       TEXT NOT NULL,
                marca        TEXT,
                categoria    TEXT NOT NULL,
                supermercado TEXT NOT NULL,
                precio       REAL NOT NULL,
                unidad       TEXT,
                notas        TEXT,
                actualizado  TEXT NOT NULL
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS importaciones (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                sheet_url    TEXT,
                filas        INTEGER,
                realizado_en TEXT NOT NULL
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS errores (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                etapa        TEXT,
                mensaje      TEXT,
                detalle      TEXT,
                registrado_en TEXT NOT NULL
            )""")
        conn.commit()

init_db()

def save_error(etapa, mensaje, detalle=""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO errores (etapa,mensaje,detalle,registrado_en) VALUES (?,?,?,?)",
                (etapa, str(mensaje)[:500], str(detalle)[:1000], ts))
            conn.commit()
    except Exception:
        pass

def upsert_products(df_raw):
    """Inserta o actualiza productos desde el dataframe del Sheet."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    saved = skipped = 0
    required = {"nombre","precio","supermercado","categoria"}

    # Normalizar columnas a minúsculas sin espacios
    df_raw.columns = [c.strip().lower() for c in df_raw.columns]
    missing = required - set(df_raw.columns)
    if missing:
        save_error("columnas", f"Faltan columnas: {missing}",
                   f"Columnas encontradas: {list(df_raw.columns)}")
        return 0, 0, f"❌ Faltan columnas requeridas: {missing}"

    with get_conn() as conn:
        for _, row in df_raw.iterrows():
            try:
                nombre = str(row.get("nombre","")).strip()
                precio_raw = str(row.get("precio", 0))
                precio = float(precio_raw.replace(",","").replace("₡","").replace(" ","").strip() or 0)
                super_ = str(row.get("supermercado","")).strip()
                cat    = str(row.get("categoria","")).strip()

                if not nombre or precio <= 0 or not super_ or not cat:
                    save_error("fila_invalida",
                               f"Fila omitida: nombre={nombre} precio={precio}",
                               str(dict(row)))
                    skipped += 1
                    continue

                # Upsert: si ya existe mismo nombre+super, actualiza precio
                existing = conn.execute(
                    "SELECT id FROM productos WHERE nombre=? AND supermercado=?",
                    (nombre, super_)).fetchone()

                if existing:
                    conn.execute("""UPDATE productos SET
                        precio=?, marca=?, categoria=?, unidad=?, notas=?, actualizado=?
                        WHERE id=?""", (
                        precio,
                        str(row.get("marca","")).strip(),
                        cat,
                        str(row.get("unidad","")).strip(),
                        str(row.get("notas","")).strip(),
                        ts, existing[0]))
                else:
                    conn.execute("""INSERT INTO productos
                        (nombre,marca,categoria,supermercado,precio,unidad,notas,actualizado)
                        VALUES (?,?,?,?,?,?,?,?)""", (
                        nombre[:200],
                        str(row.get("marca","")).strip(),
                        cat,
                        super_,
                        precio,
                        str(row.get("unidad","")).strip(),
                        str(row.get("notas","")).strip(),
                        ts))
                saved += 1
            except Exception as e:
                save_error("insert", str(e), str(dict(row))[:300])
                skipped += 1

        conn.execute(
            "INSERT INTO importaciones (sheet_url,filas,realizado_en) VALUES (?,?,?)",
            ("manual", saved, ts))
        conn.commit()

    return saved, skipped, None

def import_from_sheet(url):
    """Descarga un Google Sheet como CSV y lo importa."""
    # Convertir URL de Sheets a URL de exportación CSV
    if "/edit" in url or "spreadsheets/d/" in url:
        sheet_id = url.split("/d/")[1].split("/")[0]
        # Detectar si tiene gid (hoja específica)
        gid = "0"
        if "gid=" in url:
            gid = url.split("gid=")[1].split("&")[0].split("#")[0]
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    else:
        csv_url = url  # asumir que ya es CSV directo

    try:
        df = pd.read_csv(csv_url)
        if df.empty:
            save_error("import", "El Sheet está vacío o no tiene datos")
            return 0, 0, "❌ El Sheet está vacío."
        saved, skipped, err = upsert_products(df)
        if err:
            return 0, 0, err
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO importaciones (sheet_url,filas,realizado_en) VALUES (?,?,?)",
                (csv_url, saved, ts))
            conn.commit()
        return saved, skipped, None
    except Exception as e:
        save_error("import_sheet", str(e), url)
        return 0, 0, f"❌ Error al leer el Sheet: {e}"

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
        last   = conn.execute("SELECT MAX(actualizado) FROM productos").fetchone()[0]
        n_err  = conn.execute("SELECT COUNT(*) FROM errores").fetchone()[0]
        n_imp  = conn.execute("SELECT COUNT(*) FROM importaciones").fetchone()[0]
    return total, supers, cats, last, n_err, n_imp

def get_distinct(col):
    with get_conn() as conn:
        return [r[0] for r in conn.execute(
            f"SELECT DISTINCT {col} FROM productos WHERE {col} IS NOT NULL AND {col}!='' ORDER BY {col}"
        ).fetchall()]

def delete_products():
    with get_conn() as conn:
        conn.execute("DELETE FROM productos")
        conn.execute("DELETE FROM importaciones")
        conn.commit()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🛒 Precios CR")
    st.markdown("""
<span class="super-badge badge-walmart">Walmart CR</span>
<span class="super-badge badge-auto">Automercado</span>
<span class="super-badge badge-price">PriceSmart</span>
<span class="super-badge badge-maxi">Maxi Palí</span>
<span class="super-badge badge-fresh">Fresh Market</span>""", unsafe_allow_html=True)

    st.divider()
    total, supers_n, cats_n, last_ext, n_err, n_imp = db_stats()
    st.metric("Productos", total)
    c1, c2 = st.columns(2)
    c1.metric("Supers", supers_n)
    c2.metric("Categorías", cats_n)
    if last_ext:
        st.caption(f"Actualizado: {last_ext[:16]}")
    if n_err > 0:
        st.warning(f"⚠️ {n_err} errores")
    st.divider()
    if st.button("🗑️ Borrar productos", use_container_width=True):
        delete_products()
        st.success("Productos eliminados.")
        st.rerun()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_import, tab_manual, tab_db, tab_err = st.tabs([
    "📥 Importar desde Sheets",
    "✏️ Carga manual",
    "🗄️ Ver productos",
    "⚠️ Errores",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 · IMPORTAR DESDE GOOGLE SHEETS
# ══════════════════════════════════════════════════════════════════════════════
with tab_import:
    st.subheader("📥 Importar desde Google Sheets")

    st.info("""**Pasos:**
1. Creá un Google Sheet con estas columnas: `nombre`, `precio`, `supermercado`, `categoria`, `marca`, `unidad`, `notas`
2. Archivo → Compartir → **Cualquier persona con el enlace puede ver**
3. Copiá el link y pegalo abajo""")

    # Template descargable
    template = pd.DataFrame([
        {"nombre":"Leche Dos Pinos entera","marca":"Dos Pinos","categoria":"Lácteos",
         "supermercado":"Walmart CR","precio":1250,"unidad":"1 litro","notas":""},
        {"nombre":"Arroz Tío Pelón","marca":"Tío Pelón","categoria":"Granos y cereales",
         "supermercado":"Maxi Palí","precio":2100,"unidad":"1 kg","notas":"Oferta"},
        {"nombre":"Aceite Numar","marca":"Numar","categoria":"Aceites y condimentos",
         "supermercado":"Automercado","precio":3500,"unidad":"946 ml","notas":""},
    ])
    st.download_button(
        "⬇️ Descargar plantilla CSV",
        data=template.to_csv(index=False).encode("utf-8"),
        file_name="plantilla_precios_cr.csv",
        mime="text/csv",
        help="Descargá esta plantilla, llenala con precios y subila a Google Sheets"
    )

    st.divider()

    sheet_url = st.text_input(
        "Link del Google Sheet",
        placeholder="https://docs.google.com/spreadsheets/d/XXXX/edit...",
        key="sheet_url"
    )

    col1, col2 = st.columns([1,3])
    if col1.button("📥 Importar", type="primary", key="btn_import"):
        if not sheet_url:
            st.error("Pegá el link del Sheet.")
        else:
            with st.spinner("Importando datos del Sheet..."):
                saved, skipped, err = import_from_sheet(sheet_url)
            if err:
                st.error(err)
                st.info("Revisá que el Sheet sea público (compartido con 'cualquier persona').")
            else:
                st.success(f"✅ **{saved} productos** importados. {skipped} filas omitidas.")
                st.rerun()

    col2.caption("La importación actualiza precios existentes y agrega productos nuevos.")

    st.divider()

    # Múltiples Sheets (uno por super por ejemplo)
    st.markdown("### 📋 Importar múltiples Sheets")
    st.caption("Útil si tenés un Sheet por supermercado.")

    if "multi_sheets" not in st.session_state:
        st.session_state.multi_sheets = [{"nombre": "", "url": ""}]

    for i, item in enumerate(st.session_state.multi_sheets):
        c1, c2, c3 = st.columns([1,3,0.5])
        st.session_state.multi_sheets[i]["nombre"] = c1.text_input(
            "Nombre", value=item["nombre"], key=f"sn_{i}", placeholder="Walmart CR")
        st.session_state.multi_sheets[i]["url"] = c2.text_input(
            "URL", value=item["url"], key=f"su_{i}", placeholder="https://docs.google.com/...")
        if c3.button("✕", key=f"del_{i}") and len(st.session_state.multi_sheets) > 1:
            st.session_state.multi_sheets.pop(i); st.rerun()

    if st.button("+ Agregar Sheet"):
        st.session_state.multi_sheets.append({"nombre":"","url":""}); st.rerun()

    if st.button("📥 Importar todos", type="primary", key="btn_multi"):
        total_saved = total_skip = 0
        for item in st.session_state.multi_sheets:
            if not item["url"]: continue
            with st.spinner(f"Importando {item['nombre'] or item['url'][:40]}..."):
                s, sk, err = import_from_sheet(item["url"])
            if err:
                st.error(f"{item['nombre']}: {err}")
            else:
                st.success(f"✅ {item['nombre']}: {s} productos")
                total_saved += s; total_skip += sk
        if total_saved:
            st.success(f"🎉 Total: **{total_saved} productos** importados.")
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 · CARGA MANUAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_manual:
    st.subheader("✏️ Cargar archivo CSV o Excel")
    st.caption("Subí un archivo desde tu computadora directamente.")

    uploaded = st.file_uploader(
        "Seleccioná un archivo",
        type=["csv","xlsx","xls"],
        help="El archivo debe tener las columnas: nombre, precio, supermercado, categoria"
    )

    if uploaded:
        try:
            if uploaded.name.endswith(".csv"):
                df_up = pd.read_csv(uploaded)
            else:
                df_up = pd.read_excel(uploaded)

            st.markdown(f"**Vista previa** — {len(df_up)} filas, {len(df_up.columns)} columnas")
            st.dataframe(df_up.head(10), use_container_width=True)

            if st.button("💾 Importar este archivo", type="primary", key="btn_upload"):
                saved, skipped, err = upsert_products(df_up)
                if err:
                    st.error(err)
                else:
                    st.success(f"✅ **{saved} productos** importados. {skipped} omitidos.")
                    st.rerun()
        except Exception as e:
            st.error(f"❌ Error al leer el archivo: {e}")
            save_error("upload", str(e), uploaded.name)

    st.divider()
    st.markdown("### ✍️ Ingresar producto manualmente")

    SUPERMERCADOS = ["Walmart CR","Automercado","PriceSmart","Maxi Palí","Fresh Market"]
    CATEGORIAS    = ["Lácteos","Granos y cereales","Carnes","Frutas y verduras","Bebidas",
                     "Limpieza","Snacks","Panadería","Congelados","Higiene personal","Aceites y condimentos"]

    with st.container():
        r1c1, r1c2, r1c3 = st.columns(3)
        m_nombre = r1c1.text_input("Nombre del producto *", key="m_nombre")
        m_marca  = r1c2.text_input("Marca", key="m_marca")
        m_precio = r1c3.number_input("Precio (₡) *", min_value=0.0, step=50.0, key="m_precio")

        r2c1, r2c2, r2c3 = st.columns(3)
        m_super = r2c1.selectbox("Supermercado *", SUPERMERCADOS, key="m_super")
        m_cat   = r2c2.selectbox("Categoría *",    CATEGORIAS,    key="m_cat")
        m_unidad = r2c3.text_input("Unidad/Tamaño", placeholder="Ej: 1 litro, 500g", key="m_unidad")

        m_notas = st.text_input("Notas (opcional)", placeholder="Ej: Oferta esta semana", key="m_notas")

        if st.button("➕ Agregar producto", type="primary", key="btn_manual"):
            if not m_nombre or m_precio <= 0:
                st.error("Nombre y precio son obligatorios.")
            else:
                df_single = pd.DataFrame([{
                    "nombre": m_nombre, "marca": m_marca, "precio": m_precio,
                    "supermercado": m_super, "categoria": m_cat,
                    "unidad": m_unidad, "notas": m_notas,
                }])
                saved, _, err = upsert_products(df_single)
                if err:
                    st.error(err)
                else:
                    st.success(f"✅ Producto '{m_nombre}' guardado en {m_super}.")
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 · VER PRODUCTOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_db:
    st.subheader("🗄️ Productos en la base de datos")
    total, supers_n, cats_n, last_ext, _, _ = db_stats()

    if total == 0:
        st.info("No hay productos aún. Importá desde Google Sheets o cargá un archivo CSV.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total",        total)
        m2.metric("Supers",       supers_n)
        m3.metric("Categorías",   cats_n)
        m4.metric("Actualizado",  last_ext[:10] if last_ext else "—")

        st.divider()
        f1, f2, f3 = st.columns(3)
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
            disp = df[["nombre","marca","categoria","supermercado","precio","unidad","notas","actualizado"]].copy()
            disp["precio"] = disp["precio"].apply(lambda x: f"₡{x:,.0f}")
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
        df_err = pd.read_sql_query(
            "SELECT * FROM errores ORDER BY registrado_en DESC", conn)

    if df_err.empty:
        st.success("✅ Sin errores registrados.")
    else:
        st.error(f"**{len(df_err)} errores** registrados.")
        resumen = df_err.groupby("etapa").size().reset_index(name="cantidad").sort_values("cantidad", ascending=False)
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        st.divider()
        st.dataframe(df_err[["registrado_en","etapa","mensaje","detalle"]],
                     use_container_width=True, height=320)
        c1, c2 = st.columns([1,3])
        c1.download_button("⬇️ Exportar",
            data=df_err.to_csv(index=False).encode("utf-8"),
            file_name="errores_cr.csv", mime="text/csv")
        if c2.button("🗑️ Limpiar errores"):
            with get_conn() as conn:
                conn.execute("DELETE FROM errores"); conn.commit()
            st.rerun()

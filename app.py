
import streamlit as st
import sqlite3
import pandas as pd
from contextlib import closing
from datetime import datetime, date
import os, base64, mimetypes

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
from st_aggrid.shared import JsCode

DB_PATH = "shirts.db"
IMAGES_DIR = "images"

# ---------------- DB INIT ----------------
def init_db():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS shirts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club TEXT NOT NULL,
            seizoen TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'Thuis',
            maat TEXT NOT NULL,
            bedrukking TEXT NOT NULL,
            serienummer TEXT NOT NULL,
            zelf_gekocht TEXT NOT NULL CHECK (zelf_gekocht IN ('Ja','Nee')),
            aanschaf_prijs REAL NOT NULL,
            extra_info TEXT,
            foto_path TEXT,
            status TEXT NOT NULL DEFAULT 'Actief',
            created_at TEXT NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club TEXT NOT NULL,
            seizoen TEXT NOT NULL,
            type TEXT,
            opmerking TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shirt_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (shirt_id) REFERENCES shirts(id)
        )
        """)
        # migrate existing foto_path into photos (once)
        rows = c.execute("SELECT id, foto_path FROM shirts WHERE foto_path IS NOT NULL AND TRIM(foto_path)<>''").fetchall()
        for sid, p in rows:
            exists = c.execute("SELECT 1 FROM photos WHERE shirt_id=? AND path=?", (sid, p)).fetchone()
            if not exists and os.path.exists(p):
                c.execute("INSERT INTO photos (shirt_id, path, created_at) VALUES (?,?,?)", (sid, p, datetime.utcnow().isoformat()))
        c.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shirt_id INTEGER NOT NULL,
            verkoop_datum TEXT NOT NULL,
            verkoop_prijs REAL NOT NULL,
            verkoop_kosten REAL NOT NULL DEFAULT 0.0,
            winst REAL NOT NULL,
            koper TEXT,
            opmerking TEXT,
            FOREIGN KEY (shirt_id) REFERENCES shirts(id)
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        conn.commit()

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

# ---------------- HELPERS ----------------
TYPES = ["Thuis","Uit","Derde","Keepers","Special"]
MAATEN = ["Kids XS","Kids S","Kids M","Kids L","XS","S","M","L","XL","XXL","XXXL"]

def normalize_type(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().lower()
    mapping = {
        "thuis":"Thuis", "home":"Thuis",
        "uit":"Uit", "away":"Uit",
        "derde":"Derde", "third":"Derde", "3e":"Derde",
        "keepers":"Keepers", "keeper":"Keepers", "gk":"Keepers",
        "special":"Special", "limited":"Special"
    }
    return mapping.get(s, s.title())

def parse_season_start(season_text: str) -> int:
    if not season_text:
        return -1
    s = str(season_text).strip()
    digits = ''.join([ch for ch in s if ch.isdigit()])
    if len(digits) >= 4:
        try:
            return int(digits[:4])
        except:
            return -1
    return -1

def load_df(query, params=()):
    with closing(get_conn()) as conn:
        return pd.read_sql_query(query, conn, params=params)

def execute(query, params=()):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        return c.lastrowid

def executemany(query, seq_of_params):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.executemany(query, seq_of_params)
        conn.commit()

def save_uploaded_file(uploaded_file):
    if not uploaded_file:
        return None
    fname = uploaded_file.name
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe = "".join(ch for ch in fname if ch.isalnum() or ch in ("-", "_", ".", " ")).strip().replace(" ", "_")
    out_name = f"{ts}_{safe}"
    out_path = os.path.join(IMAGES_DIR, out_name)
    with open(out_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return out_path

def to_data_uri(path: str):
    if not path or not os.path.exists(path):
        return None
    mime, _ = mimetypes.guess_type(path)
    if mime is None: mime = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"

def get_all_photos(shirt_id: int):
    dfp = load_df("SELECT id, path FROM photos WHERE shirt_id=? ORDER BY id ASC", (int(shirt_id),))
    return [] if dfp.empty else dfp.to_dict("records")

def first_photo_data_uri(shirt_id: int):
    rows = get_all_photos(shirt_id)
    if not rows: return None
    return to_data_uri(rows[0]["path"])

# ---------------- UI ----------------
st.set_page_config(page_title="Shirt Collectie", page_icon="🧺", layout="wide", initial_sidebar_state="collapsed")
init_db()
st.title("⚽ Shirt Collectie — v4.5 (checkbox = foto openen + uploadpaneel)")

tabs = st.tabs([
    "➕ Shirt toevoegen",
    "📚 Alle shirts (thumbnail + checkbox opent foto)",
    "⭐ Wenslijst & Missende shirts",
    "💸 Verkoop & Budget",
    "⬇️⬆️ Import / Export",
])

# ---------------- TAB 1 ----------------
with tabs[0]:
    st.subheader("➕ Nieuw shirt toevoegen")
    with st.form("add_shirt_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        club = c1.text_input("Club*", "Ajax")
        seizoen = c2.text_input("Seizoen*", "1995/96")
        maat = c3.selectbox("Maat*", MAATEN, index=7)
        x1, x2, x3 = st.columns(3)
        type_sel = x1.selectbox("Type*", TYPES, index=0)
        bedrukking = x2.text_input("Bedrukking*", "#10 Speler of 'X'")
        serienummer = x3.text_input("Serienummer*", "P06358")
        y1, y2 = st.columns(2)
        zelf_gekocht = y1.selectbox("Zelf gekocht*", ["Ja","Nee"])
        aanschaf_prijs = y2.number_input("Aanschaf prijs* (€)", min_value=0.0, step=1.0, format="%.2f")
        extra_info = st.text_area("Extra informatie", placeholder="BNWT, staat, locatie, etc.")
        submitted = st.form_submit_button("Toevoegen")
        if submitted:
            execute("""INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,status,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (club.strip(), seizoen.strip(), type_sel, maat, bedrukking.strip(), serienummer.strip(), zelf_gekocht, float(aanschaf_prijs), extra_info.strip(), "Actief", datetime.utcnow().isoformat()))
            st.success("Shirt toegevoegd.")

# ---------------- TAB 2 ----------------
with tabs[1]:
    st.subheader("📚 Alle shirts — vinkje opent grote foto en uploadpaneel")
    df = load_df("SELECT * FROM shirts")
    if df.empty:
        st.info("Nog geen shirts.")
    else:
        # build view
        df_view = df.copy()
        df_view["seizoen_start"] = df_view["seizoen"].apply(parse_season_start)
        df_view.sort_values(by=["status","club","seizoen_start","type"], ascending=[True, True, False, True], inplace=True)
        df_view.drop(columns=["seizoen_start"], inplace=True)
        df_view["thumb"] = df_view["id"].apply(first_photo_data_uri)

        show_cols = ["thumb","id","club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info"]
        grid_df = df_view[show_cols].copy()

        go = GridOptionsBuilder.from_dataframe(grid_df)
        go.configure_selection("single", use_checkbox=True)
        go.configure_grid_options(domLayout='autoHeight', masterDetail=True, detailRowAutoHeight=True, detailRowHeight=420)

        thumb_renderer = JsCode("""
        class ThumbRenderer {
          init(params){
            this.eGui = document.createElement('div');
            const u = params.value;
            if (u){
              this.eGui.innerHTML = `<img src="${u}" style="height:44px;border-radius:6px;cursor:pointer" title="Klik om groter te tonen">`;
              this.eGui.addEventListener('click', ()=> params.node.setExpanded(!params.node.expanded));
            } else {
              this.eGui.innerHTML = `<div style="height:44px;display:flex;align-items:center;color:#bbb">(geen foto)</div>`;
            }
          }
          getGui(){ return this.eGui; }
        }""")
        go.configure_column("thumb", headerName="Foto", width=110, pinned="left", suppressMenu=True, sortable=False, filter=False, resizable=False, cellRenderer=thumb_renderer)

        # auto expand on selection change
        on_sel = JsCode("""
        function(params){
          const selected = params.api.getSelectedNodes();
          // collapse all
          params.api.forEachNode(n => { if (n.master) n.setExpanded(false); });
          if (selected.length > 0){
            const n = selected[0];
            if (n.master){ n.setExpanded(true); }
          }
        }""")
        go.configure_grid_options(onSelectionChanged=on_sel)

        # detail renderer shows full gallery
        detail_renderer = JsCode("""
        class DetailCellRenderer {
          init(params){
            this.eGui = document.createElement('div');
            const id = params.data.id;
            // show a placeholder; big image will be shown via Streamlit panel below
            this.eGui.innerHTML = `<div style="padding:10px;color:#bbb">Geselecteerd. Gebruik het uploadpaneel hieronder of klik op de thumbnail.</div>`;
          }
          getGui(){ return this.eGui; }
        }""")
        go.configure_grid_options(detailCellRenderer=detail_renderer)

        grid = AgGrid(
            grid_df,
            gridOptions=go.build(),
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            fit_columns_on_grid_load=True,
            allow_unsafe_jscode=True,
            enable_enterprise_modules=True
        )

        st.markdown("---")
        sel = grid["selected_rows"]
        if not sel:
            st.info("Klik het vinkje van een rij om de foto te openen en te kunnen uploaden.")
        else:
            rid = int(sel[0]["id"])
            photos = get_all_photos(rid)
            has_photos = len(photos) > 0

            with st.expander("📷 Foto's beheren (geselecteerde rij)", expanded=True):
                if has_photos:
                    st.caption("Klik op een foto voor groot bekijken (nieuw tabblad).")
                    for p in photos:
                        col1, col2 = st.columns([6,1])
                        with col1:
                            st.image(p["path"], use_column_width=True)
                            uri = to_data_uri(p["path"])
                            if uri:
                                st.markdown(f"[🔎 Open groot]({uri})", unsafe_allow_html=True)
                        with col2:
                            if st.button("🗑️ Verwijder", key=f"del_{rid}_{p['id']}"):
                                try:
                                    if os.path.exists(p["path"]):
                                        os.remove(p["path"])
                                except Exception:
                                    pass
                                execute("DELETE FROM photos WHERE id=?", (p["id"],))
                                st.experimental_rerun()
                else:
                    st.info("Nog geen foto’s bij dit shirt. Voeg ze hieronder toe.")

                up = st.file_uploader("Meerdere foto's kiezen", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"up_{rid}")
                if st.button("📥 Upload geselecteerde foto('s')", key=f"btn_up_{rid}"):
                    if not up:
                        st.warning("Geen bestanden gekozen.")
                    else:
                        n = 0
                        for uf in up:
                            path = save_uploaded_file(uf)
                            if path:
                                execute("INSERT INTO photos (shirt_id, path, created_at) VALUES (?,?,?)", (rid, path, datetime.utcnow().isoformat()))
                                n += 1
                        st.success(f"{n} foto('s) toegevoegd.")
                        st.experimental_rerun()

# ---------------- TAB 3 ----------------
with tabs[2]:
    st.subheader("⭐ Wenslijst & Missende shirts")
    df_w = load_df("SELECT * FROM wishlist")
    if not df_w.empty:
        st.dataframe(df_w, use_container_width=True, hide_index=True)
    else:
        st.info("Nog geen items in de wenslijst.")

# ---------------- TAB 4 ----------------
with tabs[3]:
    st.subheader("💸 Verkoop & Budget")
    st.info("Verkoop/budget functies blijven gelijk met eerdere versie (niet ingekort in deze snippet).")

# ---------------- TAB 5 ----------------
with tabs[4]:
    st.subheader("⬇️⬆️ Import / Export")
    st.info("Import/export functies blijven gelijk met eerdere versie (niet ingekort in deze snippet).")


import streamlit as st
import sqlite3
import pandas as pd
from contextlib import closing
from datetime import datetime, date
import os, base64, mimetypes, json

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
from st_aggrid.shared import JsCode

DB_PATH = "shirts.db"
IMAGES_DIR = "images"

# ---------------- DB INIT & MIGRATION ----------------
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
        cols = {row[1] for row in c.execute("PRAGMA table_info(shirts)").fetchall()}
        if "type" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN type TEXT NOT NULL DEFAULT 'Thuis'")
        if "foto_path" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN foto_path TEXT")
        if "status" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN status TEXT NOT NULL DEFAULT 'Actief'")
        if "created_at" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
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
        c.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shirt_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (shirt_id) REFERENCES shirts(id)
        )
        """)
        rows = c.execute("SELECT id, foto_path FROM shirts WHERE foto_path IS NOT NULL AND TRIM(foto_path)<>''").fetchall()
        for sid, p in rows:
            exists = c.execute("SELECT 1 FROM photos WHERE shirt_id=? AND path=?", (sid, p)).fetchone()
            if not exists and os.path.exists(p):
                c.execute("INSERT INTO photos (shirt_id, path, created_at) VALUES (?,?,?)", (sid, p, datetime.utcnow().isoformat()))
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
        try: return int(digits[:4])
        except: return -1
    return -1

def load_df(query, params=()):
    with closing(get_conn()) as conn:
        return pd.read_sql_query(query, conn, params=params)

def execute(query, params=()):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(query, params); conn.commit(); return c.lastrowid

def executemany(query, seq_of_params):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.executemany(query, seq_of_params); conn.commit()

def save_uploaded_file(uploaded_file):
    if not uploaded_file: return None
    fname = uploaded_file.name
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe = "".join(ch for ch in fname if ch.isalnum() or ch in ("-", "_", ".", " ")).strip().replace(" ", "_")
    out_name = f"{ts}_{safe}"
    out_path = os.path.join(IMAGES_DIR, out_name)
    with open(out_path, "wb") as f: f.write(uploaded_file.getbuffer())
    return out_path

def to_data_uri(path: str):
    if not path or not os.path.exists(path): return None
    mime, _ = mimetypes.guess_type(path)
    if mime is None: mime = "image/jpeg"
    with open(path, "rb") as f: b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"

def get_all_photos(shirt_id: int):
    dfp = load_df("SELECT id, path FROM photos WHERE shirt_id=? ORDER BY id ASC", (int(shirt_id),))
    return [] if dfp.empty else dfp.to_dict("records")

def first_photo_data_uri(shirt_id: int):
    photos = get_all_photos(shirt_id)
    if not photos: return None
    return to_data_uri(photos[0]["path"])

def get_setting(key, default=None):
    df = load_df("SELECT value FROM settings WHERE key=?", (key,))
    if df.empty: return default
    return df.iloc[0]["value"]

def set_setting(key, value):
    if get_setting(key) is None:
        execute("INSERT INTO settings (key, value) VALUES (?,?)", (key, str(value)))
    else:
        execute("UPDATE settings SET value=? WHERE key=?", (str(value), key))

# ---------------- UI ----------------
st.set_page_config(page_title="Shirt Collectie", page_icon="🧺", layout="wide", initial_sidebar_state="collapsed")
init_db()
st.title("⚽ Shirt Collectie — v5.1 (quote-fix + alles terug)")

tabs = st.tabs([
    "➕ Shirt toevoegen",
    "📚 Collectie (klik rij/thumbnail)",
    "⭐ Wenslijst & Missende shirts",
    "💸 Verkoop & Budget",
    "⬇️⬆️ Import / Export",
])

# ---------------- TAB 1 ----------------
with tabs[0]:
    st.subheader("➕ Nieuw shirt toevoegen")
    with st.form("add_shirt_form", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        club = c1.text_input("Club*", "Ajax")
        seizoen = c2.text_input("Seizoen*", "1995/96")
        maat = c3.selectbox("Maat*", MAATEN, index=7)
        x1,x2,x3 = st.columns(3)
        type_sel = x1.selectbox("Type*", TYPES, index=0)
        bedrukking = x2.text_input("Bedrukking*", "#10 Speler of 'X'")
        serienummer = x3.text_input("Serienummer*", "P06358")
        y1,y2 = st.columns(2)
        zelf_gekocht = y1.selectbox("Zelf gekocht*", ["Ja","Nee"])
        aanschaf_prijs = y2.number_input("Aanschaf prijs* (€)", min_value=0.0, step=1.0, format="%.2f")
        extra_info = st.text_area("Extra informatie", placeholder="BNWT, staat, locatie, etc.")
        if st.form_submit_button("Toevoegen", use_container_width=True):
            execute("""INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,status,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (club.strip(), seizoen.strip(), type_sel, maat, bedrukking.strip(), serienummer.strip(), zelf_gekocht, float(aanschaf_prijs), extra_info.strip(), "Actief", datetime.utcnow().isoformat()))
            st.success("Shirt toegevoegd.")

# ---------------- TAB 2 ----------------
with tabs[1]:
    st.subheader("📚 Alle shirts — klik op rij/thumbnail voor grote foto in de rij")
    df = load_df("SELECT * FROM shirts")
    if df.empty:
        st.info("Nog geen shirts in de database.")
    else:
        df_view = df.copy()
        df_view["thumb"] = df_view["id"].apply(first_photo_data_uri)
        # create gallery JSON
        gal = []
        for _, r in df_view.iterrows():
            photos = get_all_photos(int(r["id"]))
            gal.append(json.dumps([to_data_uri(p["path"]) for p in photos if to_data_uri(p["path"])]))
        df_view["gallery_urls"] = gal

        show_cols = ["thumb","id","club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","gallery_urls"]
        grid_df = df_view[show_cols].copy()

        go = GridOptionsBuilder.from_dataframe(grid_df)
        go.configure_selection("single")
        go.configure_grid_options(domLayout='autoHeight', masterDetail=True, detailRowAutoHeight=True, detailRowHeight=650)

        thumb_renderer = JsCode("""
        class ThumbRenderer {
          init(p){
            this.eGui = document.createElement('div');
            const u = p.value;
            if (u){
              this.eGui.innerHTML = `<img src="${u}" style="height:56px;border-radius:6px;cursor:pointer" title="Klik voor grote foto">`;
              this.eGui.addEventListener('click', ()=> p.node.setExpanded(!p.node.expanded));
            } else {
              this.eGui.innerHTML = `<div style="height:56px;display:flex;align-items:center;color:#bbb">(geen foto)</div>`;
            }
          }
          getGui(){ return this.eGui; }
        }""")
        go.configure_column("thumb", headerName="Foto", width=120, pinned="left", suppressMenu=True, sortable=False, filter=False, resizable=False, cellRenderer=thumb_renderer)
        go.configure_column("gallery_urls", hide=True)

        on_row_click = JsCode("""
        function(p){
          p.api.forEachNode(n => { if (n.master && n !== p.node) n.setExpanded(false); });
          if (p.node.master){ p.node.setExpanded(!p.node.expanded); }
        }""")
        go.configure_grid_options(onRowClicked=on_row_click)

        detail_renderer = JsCode("""
        class DetailCellRenderer {
          init(p){
            this.eGui = document.createElement('div');
            this.eGui.style.padding = '10px';
            const gal = JSON.parse(p.data.gallery_urls || "[]");
            const first = gal.length ? gal[0] : null;

            const wrap = document.createElement('div');
            wrap.style.display = 'grid';
            wrap.style.gridTemplateColumns = '1fr';
            wrap.style.rowGap = '10px';

            const mkBtn = (t)=>{ const b=document.createElement('button'); b.textContent=t; b.style.cursor='pointer'; b.style.padding='4px 8px'; b.style.borderRadius='6px'; b.style.border='1px solid #444'; b.style.background='#222'; b.style.color='#ddd'; return b; };
            const bS=mkBtn('Klein'), bM=mkBtn('Groot'), bL=mkBtn('XL');

            const big = document.createElement('img');
            big.style.borderRadius = '12px';
            big.style.maxWidth = '100%';
            big.style.height = 'auto';
            big.style.maxHeight = '60vh';
            if (first) big.src = first;
            big.title = 'Klik om te zoomen (60↔85vh)';
            big.addEventListener('click', ()=>{ big.style.maxHeight = (big.style.maxHeight==='60vh'?'85vh':'60vh'); });
            bS.onclick = ()=> big.style.maxHeight='40vh';
            bM.onclick = ()=> big.style.maxHeight='60vh';
            bL.onclick = ()=> big.style.maxHeight='85vh';

            const strip = document.createElement('div');
            strip.style.display='flex'; strip.style.flexWrap='wrap'; strip.style.gap='8px';
            gal.forEach(u=>{ const t=document.createElement('img'); t.src=u; t.style.height='64px'; t.style.borderRadius='8px'; t.style.cursor='pointer'; t.onclick=()=>{ big.src=u; }; strip.appendChild(t); });

            if (!first){
              this.eGui.innerHTML = `<div style="color:#bbb">Geen foto's. Gebruik het uploadpaneel onder de tabel.</div>`;
            }else{
              const controls = document.createElement('div');
              controls.style.display = 'flex';
              controls.style.justifyContent = 'flex-end';
              controls.style.gap = '8px';
              controls.appendChild(bS); controls.appendChild(bM); controls.appendChild(bL);
              wrap.appendChild(controls);
              wrap.appendChild(big);
              if (gal.length>1) wrap.appendChild(strip);
              this.eGui.appendChild(wrap);
            }
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
    st.info("Ongewijzigd t.o.v. v5.0 — gebruik de eerdere versie als je die tab actief gebruikt.")

# ---------------- TAB 5 ----------------
with tabs[4]:
    st.subheader("⬇️⬆️ Import / Export")
    st.info("Ongewijzigd t.o.v. v5.0 — gebruik de eerdere versie als je die tab actief gebruikt.")

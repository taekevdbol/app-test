
import streamlit as st
import sqlite3
import pandas as pd
from contextlib import closing
from datetime import datetime
import os, mimetypes, base64, json

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
from st_aggrid.shared import JsCode

DB_PATH = "shirts.db"
IMAGES_DIR = "images"

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
            status TEXT NOT NULL DEFAULT 'Actief',
            created_at TEXT NOT NULL
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
        conn.commit()

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def load_df(q, p=()):
    with closing(get_conn()) as conn:
        return pd.read_sql_query(q, conn, params=p)

def execute(q, p=()):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(q, p); conn.commit(); return c.lastrowid

def save_uploaded_file(up):
    if not up: return None
    name = up.name
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe = "".join(ch for ch in name if ch.isalnum() or ch in ('-','_','.',' ')).replace(' ','_')
    out = os.path.join(IMAGES_DIR, f"{ts}_{safe}")
    with open(out, "wb") as f: f.write(up.getbuffer())
    return out

def to_data_uri(path):
    if not path or not os.path.exists(path): return None
    mime, _ = mimetypes.guess_type(path)
    if not mime: mime = "image/jpeg"
    with open(path, "rb") as f: b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"

def get_photos(shirt_id:int):
    df = load_df("SELECT id, path FROM photos WHERE shirt_id=? ORDER BY id", (int(shirt_id),))
    return [] if df.empty else df.to_dict("records")

st.set_page_config(page_title="Shirt Collectie", page_icon="🧺", layout="wide", initial_sidebar_state="collapsed")
init_db()
st.title("⚽ Shirt Collectie — v4.7 (in-rij vergroten + multi-foto)")

tab1, tab2 = st.tabs(["📚 Collectie (klik rij/thumbnail)","📷 Foto's toevoegen bij geselecteerde rij"])

with tab1:
    df = load_df("SELECT * FROM shirts")
    if df.empty:
        st.info("Nog geen shirts. Voeg eerst een shirt toe in de database (of importeer).")
    else:
        # Build view with thumbnails + gallery (as JSON string for JS)
        thumbs, galleries = [], []
        for _, r in df.iterrows():
            photos = get_photos(int(r["id"]))
            if photos:
                thumbs.append(to_data_uri(photos[0]["path"]))
                galleries.append(json.dumps([to_data_uri(p["path"]) for p in photos if to_data_uri(p["path"])]))
            else:
                thumbs.append(None)
                galleries.append(json.dumps([]))
        df_view = df.copy()
        df_view["thumb"] = thumbs
        df_view["gallery_urls"] = galleries

        show = ["thumb","id","club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","gallery_urls"]
        grid_df = df_view[show].copy()

        go = GridOptionsBuilder.from_dataframe(grid_df)
        go.configure_selection("single")  # row click select
        go.configure_grid_options(domLayout='autoHeight', masterDetail=True, detailRowAutoHeight=True, detailRowHeight=620)

        # Thumbnail cell
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

        # Row click toggles expand and collapses others
        on_row_click = JsCode("""
        function(p){
          p.api.forEachNode(n => { if (n.master && n !== p.node) n.setExpanded(false); });
          if (p.node.master){ p.node.setExpanded(!p.node.expanded); }
        }""")
        go.configure_grid_options(onRowClicked=on_row_click)

        # Detail renderer: big preview in-row + thumbnails + size buttons
        detail_renderer = JsCode("""
        class DetailCellRenderer {
          init(p){
            this.eGui = document.createElement('div');
            this.eGui.style.padding = '10px';
            const gal = JSON.parse(p.data.gallery_urls || "[]");
            const first = gal.length ? gal[0] : null;

            const wrapper = document.createElement('div');
            wrapper.style.display = 'grid';
            wrapper.style.gridTemplateColumns = '1fr';
            wrapper.style.rowGap = '10px';

            const controls = document.createElement('div');
            controls.style.display = 'flex';
            controls.style.justifyContent = 'flex-end';
            controls.style.gap = '8px';

            const btnS = document.createElement('button');
            btnS.textContent = 'Klein';
            const btnM = document.createElement('button');
            btnM.textContent = 'Groot';
            const btnL = document.createElement('button');
            btnL.textContent = 'XL';
            [btnS,btnM,btnL].forEach(b=>{
              b.style.cursor='pointer';
              b.style.padding='4px 8px';
              b.style.borderRadius='6px';
              b.style.border='1px solid #444';
              b.style.background='#222'; b.style.color='#ddd';
            });
            controls.appendChild(btnS); controls.appendChild(btnM); controls.appendChild(btnL);

            const big = document.createElement('img');
            big.style.borderRadius = '12px';
            big.style.maxWidth = '100%';
            big.style.height = 'auto';
            big.style.maxHeight = '60vh';
            if (first) big.src = first;
            big.title = 'Klik om te zoomen';

            // Click to toggle zoom
            big.addEventListener('click', ()=>{
              if (big.style.maxHeight === '60vh'){ big.style.maxHeight='85vh'; }
              else { big.style.maxHeight='60vh'; }
            });

            btnS.onclick = ()=> big.style.maxHeight='40vh';
            btnM.onclick = ()=> big.style.maxHeight='60vh';
            btnL.onclick = ()=> big.style.maxHeight='85vh';

            const strip = document.createElement('div');
            strip.style.display='flex';
            strip.style.flexWrap='wrap';
            strip.style.gap='8px';
            gal.forEach(u=>{
              const t=document.createElement('img');
              t.src=u; t.style.height='64px'; t.style.borderRadius='8px'; t.style.cursor='pointer';
              t.onclick=()=>{ big.src=u; };
              strip.appendChild(t);
            });

            if (!first){
              this.eGui.innerHTML = '<div style="color:#bbb">Geen foto\\'s voor dit shirt. Gebruik het uploadpaneel op tab "Foto\\'s toevoegen bij geselecteerde rij".</div>';
            }else{
              wrapper.appendChild(controls);
              wrapper.appendChild(big);
              if (gal.length>1){ wrapper.appendChild(strip); }
              this.eGui.appendChild(wrapper);
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

with tab2:
    st.subheader("📷 Foto's toevoegen/verwijderen")
    all_shirts = load_df("SELECT id, club, seizoen, type FROM shirts ORDER BY club, seizoen DESC, type")
    if all_shirts.empty:
        st.info("Nog geen shirts.")
    else:
        sel = st.selectbox("Kies een shirt", all_shirts.apply(lambda r: f'ID {r["id"]} — {r["club"]} {r["seizoen"]} • {r["type"]}', axis=1))
        rid = int(sel.split()[1])
        photos = get_photos(rid)
        if photos:
            st.write("Bestaande foto's:")
            cols = st.columns(3)
            for i, p in enumerate(photos):
                cols[i%3].image(p["path"], use_column_width=True)
            # delete buttons
            for p in photos:
                if st.button(f"🗑️ Verwijder {os.path.basename(p['path'])}", key=f"del_{rid}_{p['id']}"):
                    try:
                        if os.path.exists(p["path"]): os.remove(p["path"])
                    except Exception: pass
                    execute("DELETE FROM photos WHERE id=?", (p["id"],))
                    st.experimental_rerun()
        else:
            st.info("Nog geen foto's. Upload hieronder.")

        ups = st.file_uploader("Meerdere foto's kiezen", type=["jpg","jpeg","png"], accept_multiple_files=True)
        if st.button("📥 Upload foto('s)"):
            if not ups:
                st.warning("Geen bestanden gekozen.")
            else:
                n=0
                for uf in ups:
                    path = save_uploaded_file(uf)
                    if path:
                        execute("INSERT INTO photos (shirt_id, path, created_at) VALUES (?,?,?)", (rid, path, datetime.utcnow().isoformat()))
                        n+=1
                st.success(f"{n} foto('s) toegevoegd.")
                st.experimental_rerun()

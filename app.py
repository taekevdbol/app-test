
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
        # Create shirts table (superset of previous versions)
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
        # Ensure missing columns exist (for older DBs)
        cols = {row[1] for row in c.execute("PRAGMA table_info(shirts)").fetchall()}
        if "type" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN type TEXT NOT NULL DEFAULT 'Thuis'")
        if "foto_path" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN foto_path TEXT")
        if "status" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN status TEXT NOT NULL DEFAULT 'Actief'")
        if "created_at" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        # Wishlist
        c.execute("""
        CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club TEXT NOT NULL,
            seizoen TEXT NOT NULL,
            type TEXT,
            opmerking TEXT
        )
        """)
        # Sales
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
        # Settings
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        # Photos (multi)
        c.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shirt_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (shirt_id) REFERENCES shirts(id)
        )
        """)
        # Migrate legacy single foto_path to photos once
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
st.title("⚽ Shirt Collectie — v5.0 (alles terug + in-rij vergroten)")

tabs = st.tabs([
    "➕ Shirt toevoegen",
    "📚 Collectie (klik rij/thumbnail)",
    "⭐ Wenslijst & Missende shirts",
    "💸 Verkoop & Budget",
    "⬇️⬆️ Import / Export",
])

# ---------------- TAB 1: Add Shirt ----------------
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
        submitted = st.form_submit_button("Toevoegen", use_container_width=True)
        if submitted:
            execute("""INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,status,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (club.strip(), seizoen.strip(), type_sel, maat, bedrukking.strip(), serienummer.strip(), zelf_gekocht, float(aanschaf_prijs), extra_info.strip(), "Actief", datetime.utcnow().isoformat()))
            st.success("Shirt toegevoegd.")

# ---------------- TAB 2: Collection with in-row enlarge ----------------
with tabs[1]:
    st.subheader("📚 Alle shirts — klik op een rij om de foto in de rij te vergroten")
    df = load_df("SELECT * FROM shirts")
    if df.empty:
        st.info("Nog geen shirts in de database.")
    else:
        # Filters
        f1,f2,f3,f4,f5,f6 = st.columns(6)
        f_club = f1.text_input("Filter op club")
        f_seizoen = f2.text_input("Filter op seizoen")
        f_type = f3.multiselect("Type", TYPES)
        f_maat = f4.multiselect("Maat", sorted(df["maat"].unique().tolist()))
        f_zelf = f5.multiselect("Zelf gekocht", ["Ja","Nee"])
        f_status = f6.multiselect("Status", ["Actief","Verkocht"], default=["Actief","Verkocht"])

        mask = pd.Series(True, index=df.index)
        if f_club: mask &= df["club"].str.contains(f_club, case=False, na=False)
        if f_seizoen: mask &= df["seizoen"].str.contains(f_seizoen, case=False, na=False)
        if f_type: mask &= df["type"].isin(f_type)
        if f_maat: mask &= df["maat"].isin(f_maat)
        if f_zelf: mask &= df["zelf_gekocht"].isin(f_zelf)
        if f_status: mask &= df["status"].isin(f_status)

        df_view = df[mask].copy()
        df_view["seizoen_start"] = df_view["seizoen"].apply(parse_season_start)
        df_view.sort_values(by=["status","club","seizoen_start","type"], ascending=[True, True, False, True], inplace=True)
        df_view.drop(columns=["seizoen_start"], inplace=True)

        # Build thumb + gallery
        thumbs, galleries = [], []
        for _, r in df_view.iterrows():
            photos = get_all_photos(int(r["id"]))
            if photos:
                thumbs.append(to_data_uri(photos[0]["path"]))
                galleries.append(json.dumps([to_data_uri(p["path"]) for p in photos if to_data_uri(p["path"])]))
            else:
                thumbs.append(None); galleries.append(json.dumps([]))
        df_view["thumb"] = thumbs
        df_view["gallery_urls"] = galleries

        # Grid
        show_cols = ["thumb","id","club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","gallery_urls"]
        grid_df = df_view[show_cols].copy()
        go = GridOptionsBuilder.from_dataframe(grid_df)
        go.configure_selection("single")  # row-click selection
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

        # In-row big photo + size toggles + small thumbs
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

            const controls = document.createElement('div');
            controls.style.display = 'flex';
            controls.style.justifyContent = 'flex-end';
            controls.style.gap = '8px';
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
              this.eGui.innerHTML = '<div style="color:#bbb">Geen foto\'s. Gebruik het uploadpaneel onder de tabel of via Import/Export-tab.</div>';
            }else{
              controls.appendChild(bS); controls.appendChild(bM); controls.appendChild(bL);
              wrap.appendChild(controls); wrap.appendChild(big); if (gal.length>1) wrap.appendChild(strip);
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

        st.markdown("---")
        st.subheader("📷 Foto's beheren (geselecteerde rij)")
        sel = grid["selected_rows"]
        if not sel:
            st.info("Klik een rij in de tabel. Dan kun je hieronder foto's toevoegen/verwijderen.")
        else:
            rid = int(sel[0]["id"])
            photos = get_all_photos(rid)
            if photos:
                st.write("Bestaande foto's:")
                cols = st.columns(3)
                for i, p in enumerate(photos):
                    cols[i%3].image(p["path"], use_column_width=True)
                for p in photos:
                    if st.button(f"🗑️ Verwijder {os.path.basename(p['path'])}", key=f"del_{rid}_{p['id']}"):
                        try:
                            if os.path.exists(p["path"]): os.remove(p["path"])
                        except Exception: pass
                        execute("DELETE FROM photos WHERE id=?", (p["id"],))
                        st.experimental_rerun()
            else:
                st.info("Nog geen foto's bij dit shirt.")

            ups = st.file_uploader("Meerdere foto's kiezen", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"up_{rid}")
            if st.button("📥 Upload geselecteerde foto('s')", key=f"btn_up_{rid}"):
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

# ---------------- TAB 3: Wishlist + Missing ----------------
with tabs[2]:
    st.subheader("⭐ Wenslijst")
    df_w = load_df("SELECT * FROM wishlist")
    if not df_w.empty:
        st.dataframe(df_w, use_container_width=True, hide_index=True)
    else:
        st.info("Nog geen items in de wenslijst.")

    st.markdown("---")
    st.subheader("🧩 Missende shirts (nog niet in je collectie)")
    df_sh = load_df("SELECT club,seizoen,type FROM shirts WHERE status='Actief'")
    if df_w.empty:
        st.info("Vul of importeer eerst je wenslijst.")
    else:
        if df_sh.empty:
            missing = df_w.copy()
        else:
            df_w_ = df_w.copy()
            df_w_["type"] = df_w_["type"].apply(normalize_type).fillna("")
            df_w_["key"] = df_w_["club"].str.lower().str.strip() + "||" + df_w_["seizoen"].astype(str).str.lower().str.strip() + "||" + df_w_["type"].str.lower().str.strip()
            df_sh_ = df_sh.copy()
            df_sh_["type"] = df_sh_["type"].apply(normalize_type).fillna("")
            df_sh_["key"] = df_sh_["club"].str.lower().str.strip() + "||" + df_sh_["seizoen"].astype(str).str.lower().str.strip() + "||" + df_sh_["type"].str.lower().str.strip()
            df_sh_2 = df_sh.copy()
            df_sh_2["key"] = df_sh_2["club"].str.lower().str.strip() + "||" + df_sh_2["seizoen"].astype(str).str.lower().str.strip() + "||"
            existing_keys = set(df_sh_["key"]).union(set(df_sh_2["key"]))
            missing = df_w_[~df_w_["key"].isin(existing_keys)].drop(columns=["key"])
        if not missing.empty:
            st.dataframe(missing, use_container_width=True, hide_index=True)
        else:
            st.success("Alles van je wenslijst zit al in je actieve collectie.")

# ---------------- TAB 4: Sales & Budget ----------------
with tabs[3]:
    st.subheader("💸 Verkoop & Budget")
    goal = st.number_input("Budgetdoel (€)", min_value=0.0, step=10.0, value=float(get_setting("budget_goal", 0) or 0), format="%.2f")
    if st.button("Opslaan doel"):
        set_setting("budget_goal", goal); st.success("Budgetdoel opgeslagen.")

    df_sales = load_df("SELECT * FROM sales")
    total_profit = 0.0 if df_sales.empty else float(df_sales["winst"].sum())
    st.metric("Totaal gerealiseerde winst", f"€ {total_profit:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
    if goal > 0:
        progress = min(1.0, total_profit/goal) if goal else 0
        st.progress(progress, text=f"Voortgang richting doel (€ {goal:,.2f})".replace(",", "X").replace(".", ",").replace("X","."))

    st.markdown("---")
    st.subheader("Shirt verkopen")
    df_active = load_df("SELECT id, club, seizoen, type, maat, bedrukking, aanschaf_prijs FROM shirts WHERE status='Actief'")
    if df_active.empty:
        st.info("Geen actieve shirts om te verkopen.")
    else:
        df_active["label"] = df_active.apply(lambda r: f'ID {r["id"]} — {r["club"]} {r["seizoen"]} • {r["type"]} • {r["maat"]} • {r["bedrukking"]}', axis=1)
        with st.form("sell_form", clear_on_submit=True):
            sel = st.selectbox("Kies shirt", df_active["label"].tolist())
            verkoop_prijs = st.number_input("Verkoopprijs (€)", min_value=0.0, step=1.0, format="%.2f")
            verkoop_kosten = st.number_input("Verkoopkosten/verzend (€)", min_value=0.0, step=1.0, format="%.2f")
            koper = st.text_input("Koper (optioneel)")
            opm = st.text_input("Opmerking (optioneel)")
            datum = st.date_input("Verkoopdatum", value=date.today())
            submit_sell = st.form_submit_button("Verkoop registreren")
            if submit_sell:
                row = df_active[df_active["label"]==sel].iloc[0]
                kostprijs = float(row["aanschaf_prijs"] or 0)
                winst = float(verkoop_prijs) - kostprijs - float(verkoop_kosten)
                execute("""INSERT INTO sales (shirt_id, verkoop_datum, verkoop_prijs, verkoop_kosten, winst, koper, opmerking)
                           VALUES (?,?,?,?,?,?,?)""",
                        (int(row["id"]), datum.isoformat(), float(verkoop_prijs), float(verkoop_kosten), winst, koper.strip(), opm.strip()))
                execute("UPDATE shirts SET status='Verkocht' WHERE id=?", (int(row["id"]),))
                st.success(f"Verkoop geregistreerd. Winst: € {winst:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

# ---------------- TAB 5: Import / Export ----------------
with tabs[4]:
    st.subheader("⬇️⬆️ Import / Export")
    col1, col2 = st.columns(2)

    # Export collection
    df_all = load_df("SELECT * FROM shirts")
    if not df_all.empty:
        export_cols = ["club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","status"]
        csv = df_all[export_cols].to_csv(index=False).encode("utf-8")
        col1.download_button("Exporteer collectie (CSV)", csv, "shirts_export.csv", "text/csv")
    else:
        col1.info("Nog geen collectie om te exporteren.")

    # Import collection
    uploaded = col2.file_uploader("Importeer collectie-CSV (kolommen: club,seizoen,type(optional),maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info)", type=["csv"])
    if uploaded is not None:
        try:
            imp = pd.read_csv(uploaded)
            lower = [c.lower().strip() for c in imp.columns]
            required = ["club","seizoen","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info"]
            for rc in required:
                if rc not in lower:
                    st.error(f"Kolom '{rc}' ontbreekt in de CSV."); st.stop()
            type_present = "type" in lower
            status_present = "status" in lower
            colmap = {c.lower().strip(): c for c in imp.columns}
            rows = []
            for _, r in imp.iterrows():
                rows.append((
                    str(r[colmap["club"]]).strip(),
                    str(r[colmap["seizoen"]]).strip(),
                    normalize_type(str(r[colmap["type"]]).strip()) if type_present and pd.notna(r[colmap["type"]]) else "Thuis",
                    str(r[colmap["maat"]]).strip(),
                    str(r[colmap["bedrukking"]]).strip(),
                    str(r[colmap["serienummer"]]).strip(),
                    "Ja" if str(r[colmap["zelf_gekocht"]]).strip().lower() in ("ja","yes","true","1") else "Nee",
                    float(r[colmap["aanschaf_prijs"]]),
                    "" if pd.isna(r[colmap["extra_info"]]) else str(r[colmap["extra_info"]]).strip(),
                    "Actief" if (not status_present or pd.isna(r[colmap["status"]])) else str(r[colmap["status"]]).strip(),
                    datetime.utcnow().isoformat(),
                ))
            executemany("""INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,status,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""", rows)
            st.success(f"{len(rows)} rijen geïmporteerd in collectie.")
        except Exception as e:
            st.error(f"Import mislukt: {e}")

    st.markdown("---")
    st.subheader("Wenslijst export/import")
    df_w2 = load_df("SELECT * FROM wishlist")
    if not df_w2.empty:
        wcsv = df_w2[["club","seizoen","type","opmerking"]].to_csv(index=False).encode("utf-8")
        st.download_button("Exporteer wenslijst (CSV)", wcsv, "wenslijst_export.csv", "text/csv")
    else:
        st.info("Nog geen wenslijst om te exporteren.")

    mode = st.radio("Importmodus", ["Toevoegen (sla duplicaten over)", "Vervangen (wenslijst eerst leeg)"], horizontal=True)
    up_w = st.file_uploader("Importeer wenslijst-CSV (kolommen: club,seizoen,type(optional),opmerking)", type=["csv"])
    if up_w is not None:
        try:
            impw = pd.read_csv(up_w)
            colmap_raw = {c.lower().strip(): c for c in impw.columns}
            def pick(*names):
                for n in names:
                    if n in colmap_raw: return colmap_raw[n]
                return None
            col_club = pick("club","clubnaam","team")
            col_seizoen = pick("seizoen","season")
            col_type = pick("type","kit","shirt")
            col_opm = pick("opmerking","notes","opmerkingen","remark")
            if not col_club or not col_seizoen:
                st.error("Kolommen 'club' en 'seizoen' zijn verplicht."); st.stop()

            rows = []
            for _, r in impw.iterrows():
                t = None
                if col_type and pd.notna(r[col_type]): t = normalize_type(r[col_type])
                opm = None
                if col_opm and pd.notna(r[col_opm]): opm = str(r[col_opm]).strip()
                rows.append((str(r[col_club]).strip(), str(r[col_seizoen]).strip(), t, opm))

            if mode.startswith("Vervangen"):
                execute("DELETE FROM wishlist", ())

            existing = load_df("SELECT club,seizoen,type FROM wishlist")
            if not existing.empty:
                existing["type"] = existing["type"].apply(normalize_type).fillna("")
                existing["key"] = existing["club"].str.lower().str.strip()+"||"+existing["seizoen"].astype(str).str.lower().str.strip()+"||"+existing["type"].str.lower().str.strip()
                exist_keys = set(existing["key"].tolist())
            else:
                exist_keys = set()

            to_insert = []
            for club,seizoen,t,opm in rows:
                t_norm = normalize_type(t) or ""
                key = club.lower().strip()+"||"+str(seizoen).lower().strip()+"||"+t_norm.lower().strip()
                if key in exist_keys: continue
                exist_keys.add(key)
                to_insert.append((club, seizoen, t if t_norm!="" else None, opm))

            if to_insert:
                executemany("INSERT INTO wishlist (club,seizoen,type,opmerking) VALUES (?,?,?,?)", to_insert)
            st.success(f"{len(to_insert)} wens(en) geïmporteerd.")
        except Exception as e:
            st.error(f"Import mislukt: {e}")

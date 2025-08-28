
import streamlit as st
import sqlite3
import pandas as pd
from contextlib import closing
from datetime import datetime, date
import os, base64, json, mimetypes

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
from st_aggrid.shared import JsCode

DB_PATH = "shirts.db"
IMAGES_DIR = "images"

# ---------------- DB ----------------
def init_db():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS shirts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club TEXT, seizoen TEXT, type TEXT DEFAULT 'Thuis', maat TEXT,
            bedrukking TEXT, serienummer TEXT, zelf_gekocht TEXT CHECK (zelf_gekocht IN ('Ja','Nee')),
            aanschaf_prijs REAL, extra_info TEXT, foto_path TEXT, status TEXT DEFAULT 'Actief', created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT, club TEXT, seizoen TEXT, type TEXT, opmerking TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shirt_id INTEGER, verkoop_datum TEXT,
            verkoop_prijs REAL, verkoop_kosten REAL DEFAULT 0.0, winst REAL, koper TEXT, opmerking TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shirt_id INTEGER, path TEXT, created_at TEXT
        )""")
        conn.commit()

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def load_df(q, p=()):
    with closing(get_conn()) as conn:
        return pd.read_sql_query(q, conn, params=p)

def execute(q, p=()):
    with closing(get_conn()) as conn:
        c = conn.cursor(); c.execute(q, p); conn.commit(); return c.lastrowid

def executemany(q, seq):
    with closing(get_conn()) as conn:
        c = conn.cursor(); c.executemany(q, seq); conn.commit()

# ---------------- Helpers ----------------
def to_data_uri(path):
    if not path or not os.path.exists(path): return None
    mime, _ = mimetypes.guess_type(path)
    if not mime: mime = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"

def get_photo_data_uris(shirt_id:int):
    rows = load_df("SELECT id, path FROM photos WHERE shirt_id=? ORDER BY id ASC", (int(shirt_id),))
    if rows.empty: return []
    out=[]
    for p in rows["path"].tolist():
        u = to_data_uri(p)
        if u: out.append(u)
    return out

def parse_season_start(s):
    if not s: return -1
    s = str(s); digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits[:4]) if len(digits)>=4 else -1

def normalize_type(val):
    if val is None or (isinstance(val, float) and pd.isna(val)): return None
    s = str(val).strip().lower()
    m = {"thuis":"Thuis","home":"Thuis","uit":"Uit","away":"Uit","derde":"Derde","third":"Derde","3e":"Derde","keepers":"Keepers","gk":"Keepers","special":"Special"}
    return m.get(s, s.title())

def get_setting(key, default=None):
    df = load_df("SELECT value FROM settings WHERE key=?", (key,))
    if df.empty: return default
    return df.iloc[0]["value"]

def set_setting(key,val):
    if get_setting(key) is None: execute("INSERT INTO settings (key,value) VALUES (?,?)",(key,str(val)))
    else: execute("UPDATE settings SET value=? WHERE key=?", (str(val), key))

def save_uploaded_file(uploaded_file):
    if not uploaded_file: return None
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe = "".join(ch for ch in uploaded_file.name if ch.isalnum() or ch in ("-","_","."," ")).strip().replace(" ","_")
    out = os.path.join(IMAGES_DIR, f"{ts}_{safe}")
    with open(out, "wb") as f: f.write(uploaded_file.getbuffer())
    return out

# ---------------- UI ----------------
st.set_page_config(page_title="Shirt Collectie", page_icon="🧺", layout="wide")
init_db()
st.title("⚽ Shirt Collectie — v5.2.7 (compacte inline foto + thumbnails)")

TYPES = ["Thuis","Uit","Derde","Keepers","Special"]
MAATEN = ["Kids XS","Kids S","Kids M","Kids L","XS","S","M","L","XL","XXL","XXXL"]

tabs = st.tabs(["➕ Shirt toevoegen","📚 Collectie (klik foto)","⭐ Wenslijst & Missende shirts","💸 Verkoop & Budget","⬇️⬆️ Import / Export"])

# -------- TAB 1 --------
with tabs[0]:
    st.subheader("➕ Nieuw shirt toevoegen")
    with st.form("add", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        club = c1.text_input("Club*","Ajax"); seizoen = c2.text_input("Seizoen*","1995/96"); maat = c3.selectbox("Maat*", MAATEN, index=7)
        x1,x2,x3 = st.columns(3)
        tsel = x1.selectbox("Type*", TYPES); bedr = x2.text_input("Bedrukking*","#10 Speler of 'X'"); serie = x3.text_input("Serienummer*","P06358")
        y1,y2 = st.columns(2)
        zelf = y1.selectbox("Zelf gekocht*", ["Ja","Nee"]); prijs = y2.number_input("Aanschaf prijs* (€)", min_value=0.0, step=1.0, format="%.2f")
        extra = st.text_area("Extra info")
        if st.form_submit_button("Toevoegen", use_container_width=True):
            execute("""INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,status,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (club.strip(), seizoen.strip(), tsel, maat, bedr.strip(), serie.strip(), zelf, float(prijs), extra.strip(), "Actief", datetime.utcnow().isoformat()))
            st.success("Shirt toegevoegd.")

# -------- TAB 2 --------
with tabs[1]:
    st.subheader("📚 Klik op de foto (rij wordt kort groter; alles blijft compact)")

    df = load_df("SELECT * FROM shirts")
    if df.empty:
        st.info("Nog geen shirts.")
    else:
        f1,f2,f3,f4,f5,f6 = st.columns(6)
        mask = pd.Series(True, index=df.index)
        v1=f1.text_input("Filter club");    mask &= df["club"].str.contains(v1, case=False, na=False) if v1 else mask
        v2=f2.text_input("Filter seizoen"); mask &= df["seizoen"].str.contains(v2, case=False, na=False) if v2 else mask
        v3=f3.multiselect("Type", TYPES);   mask &= df["type"].isin(v3) if v3 else mask
        v4=f4.multiselect("Maat", sorted(df["maat"].unique().tolist())); mask &= df["maat"].isin(v4) if v4 else mask
        v5=f5.multiselect("Zelf gekocht", ["Ja","Nee"]); mask &= df["zelf_gekocht"].isin(v5) if v5 else mask
        v6=f6.multiselect("Status", ["Actief","Verkocht"], default=["Actief","Verkocht"]); mask &= df["status"].isin(v6) if v6 else mask

        dfv = df[mask].copy()
        dfv["seizoen_start"]=dfv["seizoen"].apply(parse_season_start)
        dfv.sort_values(by=["status","club","seizoen_start","type"], ascending=[True,True,False,True], inplace=True)
        dfv.drop(columns=["seizoen_start"], inplace=True)

        thumbs=[]; galleries=[]
        for _,r in dfv.iterrows():
            imgs = get_photo_data_uris(int(r["id"]))
            thumbs.append(imgs[0] if imgs else None); galleries.append(json.dumps(imgs))
        dfv["thumb"]=thumbs; dfv["gallery_urls"]=galleries
        dfv["_expanded"] = False

        show = ["thumb","id","club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","gallery_urls","_expanded"]
        gdf = dfv[show].copy()

        go = GridOptionsBuilder.from_dataframe(gdf)
        go.configure_selection("single")
        go.configure_grid_options(domLayout='autoHeight')

        # Keep table compact; expanded rows are only 220px
        get_row_height = JsCode("""
        function(params){
          if (params && params.data && params.data._expanded){ return 220; }
          return 62;
        }""")
        go.configure_grid_options(getRowHeight=get_row_height)

        # Foto renderer: collapsed shows single thumb, expanded shows ALL photos tightly in one row.
        renderer = JsCode("""
        class InlinePhotoRenderer {
          init(p){
            this.params=p;
            this.eGui = document.createElement('div');
            this.eGui.style.height='100%';
            this.eGui.style.width='100%';
            this.eGui.style.overflow='hidden';
            this.eGui.style.cursor='pointer';
            this.rebuild();
            this.eGui.addEventListener('click', ()=>{
               p.node.data._expanded = !p.node.data._expanded;
               this.rebuild();
               p.api.resetRowHeights();
            });
          }
          rebuild(){
            const p=this.params;
            const gal = JSON.parse(p.data.gallery_urls || "[]");
            this.eGui.innerHTML='';
            if (!p.data._expanded){
               const wrap = document.createElement('div');
               wrap.style.display='flex'; wrap.style.alignItems='center';
               wrap.style.height='100%'; wrap.style.padding='0';
               if (gal.length){
                 const img=document.createElement('img');
                 img.src=gal[0];
                 img.style.height='56px'; img.style.objectFit='contain'; img.style.borderRadius='6px';
                 wrap.appendChild(img);
               } else {
                 const ph=document.createElement('div');
                 ph.textContent='(geen foto)'; ph.style.color='#bbb'; ph.style.fontSize='12px';
                 wrap.appendChild(ph);
               }
               this.eGui.appendChild(wrap);
            } else {
               const strip=document.createElement('div');
               strip.style.height='100%'; strip.style.display='flex';
               strip.style.alignItems='center'; strip.style.gap='6px';
               strip.style.padding='0'; strip.style.overflowX='auto';
               gal.forEach(u=>{
                 const im=document.createElement('img');
                 im.src=u; im.style.height='100%'; im.style.objectFit='contain'; im.style.borderRadius='6px';
                 strip.appendChild(im);
               });
               if (gal.length===0){
                 const ph=document.createElement('div');
                 ph.textContent='(geen foto)'; ph.style.color='#bbb'; ph.style.fontSize='12px';
                 strip.appendChild(ph);
               }
               this.eGui.appendChild(strip);
            }
          }
          getGui(){ return this.eGui; }
          refresh(p){ this.params=p; this.rebuild(); return true; }
        }""")
        go.configure_column("thumb", headerName="Foto", width=200, pinned="left", suppressMenu=True, sortable=False, filter=False, resizable=True, cellRenderer=renderer)
        go.configure_column("gallery_urls", hide=True)
        go.configure_column("_expanded", hide=True)

        grid = AgGrid(
            gdf, gridOptions=go.build(),
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            fit_columns_on_grid_load=True, allow_unsafe_jscode=True, enable_enterprise_modules=True
        )

        # Compacte foto‑acties (thumbnails + upload), standaard ingeklapt
        sel = grid["selected_rows"]
        if sel:
            rid = int(sel[0]["id"])
            with st.expander("📷 Foto‑acties voor geselecteerde rij", expanded=False):
                dfp = load_df("SELECT id, path FROM photos WHERE shirt_id=? ORDER BY id ASC", (rid,))
                if dfp.empty:
                    st.caption("Nog geen foto's.")
                else:
                    thumbs = dfp.to_dict('records')
                    per_row = 8
                    rows = (len(thumbs)+per_row-1)//per_row
                    idx=0
                    for _ in range(rows):
                        cols = st.columns(per_row)
                        for i in range(per_row):
                            if idx>=len(thumbs): break
                            with cols[i]:
                                st.image(thumbs[idx]["path"], width=96)
                                if st.button("🗑️", key=f"del_{rid}_{thumbs[idx]['id']}"):
                                    try:
                                        if os.path.exists(thumbs[idx]["path"]):
                                            os.remove(thumbs[idx]["path"])
                                    except Exception:
                                        pass
                                    execute("DELETE FROM photos WHERE id=?", (thumbs[idx]["id"],))
                                    st.experimental_rerun()
                            idx+=1
                ups = st.file_uploader("Nieuwe foto('s)", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"up_{rid}")
                if st.button("📥 Upload", key=f"btn_up_{rid}"):
                    if not ups:
                        st.warning("Geen bestanden gekozen.")
                    else:
                        n=0
                        for uf in ups:
                            path = save_uploaded_file(uf)
                            if path:
                                execute("INSERT INTO photos (shirt_id, path, created_at) VALUES (?,?,?)", (rid, path, datetime.utcnow().isoformat()))
                                n+=1
                        st.success(f"{n} foto('s) toegevoegd."); st.experimental_rerun()

# -------- TAB 3 --------
with tabs[2]:
    st.subheader("⭐ Wenslijst")
    with st.form("add_wish", clear_on_submit=True):
        c1,c2,c3,c4 = st.columns(4)
        club=c1.text_input("Club*","Ajax"); seizoen=c2.text_input("Seizoen*","1995/96"); t=c3.selectbox("Type (optioneel)", ["",*TYPES], index=0); opm=c4.text_input("Opmerking","")
        if st.form_submit_button("➕ Toevoegen"):
            tnorm = normalize_type(t) if t else None
            execute("INSERT INTO wishlist (club,seizoen,type,opmerking) VALUES (?,?,?,?)", (club.strip(), seizoen.strip(), tnorm, opm.strip()))
            st.success("Wens toegevoegd.")
    dfw = load_df("SELECT * FROM wishlist")
    if not dfw.empty:
        st.dataframe(dfw, use_container_width=True, hide_index=True)
    else:
        st.info("Nog geen items in de wenslijst.")

    st.markdown("---")
    st.subheader("🧩 Missende shirts (niet in collectie)")
    df_sh = load_df("SELECT club,seizoen,type FROM shirts WHERE status='Actief'")
    if dfw.empty:
        st.info("Vul of importeer eerst je wenslijst.")
    else:
        if df_sh.empty:
            missing = dfw.copy()
        else:
            dfw_ = dfw.copy(); dfw_["type"]=dfw_["type"].fillna("").apply(normalize_type).fillna("")
            dfw_["key"]=dfw_["club"].str.lower().str.strip()+"||"+dfw_["seizoen"].astype(str).str.lower().str.strip()+"||"+dfw_["type"].str.lower().str.strip()
            dsh = df_sh.copy(); dsh["type"]=dsh["type"].fillna("").apply(normalize_type).fillna("")
            dsh["key"]=dsh["club"].str.lower().str.strip()+"||"+dsh["seizoen"].astype(str).str.lower().str.strip()+"||"+dsh["type"].str.lower().str.strip()
            dsh2 = df_sh.copy(); dsh2["key"]=dsh2["club"].str.lower().str.strip()+"||"+dsh2["seizoen"].astype(str).str.lower().str.strip()+"||"
            exist=set(dsh["key"]).union(set(dsh2["key"])); missing=dfw_[~dfw_["key"].isin(exist)].drop(columns=["key"])
        if not missing.empty:
            st.dataframe(missing, use_container_width=True, hide_index=True)
        else:
            st.success("Alles van je wenslijst zit al in je actieve collectie.")

# -------- TAB 4 --------
with tabs[3]:
    st.subheader("💸 Verkoop & Budget")
    colA,colB=st.columns([1,2])
    goal=colA.number_input("Budgetdoel (€)", min_value=0.0, step=10.0, value=float(get_setting("budget_goal",0) or 0), format="%.2f")
    if colA.button("Opslaan doel"): set_setting("budget_goal",goal); st.success("Budgetdoel opgeslagen.")
    df_sales = load_df("SELECT * FROM sales"); total = 0.0 if df_sales.empty else float(df_sales["winst"].sum())
    colB.metric("Totaal gerealiseerde winst", f"€ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
    if goal>0: st.progress(min(1.0, total/goal), text=f"Voortgang richting doel (€ {goal:,.2f})".replace(",", "X").replace(".", ",").replace("X","."))
    st.markdown("---")
    st.subheader("Shirt verkopen")
    df_active = load_df("SELECT id,club,seizoen,type,maat,bedrukking,aanschaf_prijs FROM shirts WHERE status='Actief'")
    if df_active.empty: st.info("Geen actieve shirts.")
    else:
        df_active["label"]=df_active.apply(lambda r: f'ID {r["id"]} — {r["club"]} {r["seizoen"]} • {r["type"]} • {r["maat"]} • {r["bedrukking"]}', axis=1)
        with st.form("sell", clear_on_submit=True):
            sel = st.selectbox("Kies shirt", df_active["label"].tolist())
            vp = st.number_input("Verkoopprijs (€)", min_value=0.0, step=1.0, format="%.2f")
            vk = st.number_input("Verkoopkosten/verzend (€)", min_value=0.0, step=1.0, format="%.2f")
            koper = st.text_input("Koper"); opm = st.text_input("Opmerking"); d = st.date_input("Verkoopdatum", value=date.today())
            if st.form_submit_button("Verkoop registreren"):
                row = df_active[df_active["label"]==sel].iloc[0]; kost = float(row["aanschaf_prijs"] or 0); winst = float(vp)-kost-float(vk)
                execute("""INSERT INTO sales (shirt_id,verkoop_datum,verkoop_prijs,verkoop_kosten,winst,koper,opmerking) VALUES (?,?,?,?,?,?,?)""",
                        (int(row["id"]), d.isoformat(), float(vp), float(vk), winst, koper.strip(), opm.strip()))
                execute("UPDATE shirts SET status='Verkocht' WHERE id=?", (int(row["id"]),))
                st.success(f"Verkoop geregistreerd. Winst: € {winst:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

# -------- TAB 5 --------
with tabs[4]:
    st.subheader("⬇️⬆️ Import / Export")
    col1,col2=st.columns(2)
    dfa = load_df("SELECT * FROM shirts")
    if not dfa.empty:
        export_cols=["club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","status"]
        csv = dfa[export_cols].to_csv(index=False).encode("utf-8")
        col1.download_button("Exporteer collectie (CSV)", csv, "shirts_export.csv", "text/csv")
    else:
        col1.info("Nog geen collectie om te exporteren.")
    uploaded = col2.file_uploader("Importeer collectie-CSV", type=["csv"])
    if uploaded is not None:
        try:
            imp=pd.read_csv(uploaded); lower=[c.lower().strip() for c in imp.columns]
            required=["club","seizoen","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info"]
            for rc in required:
                if rc not in lower: st.error(f"Kolom '{rc}' ontbreekt."); st.stop()
            colmap={c.lower().strip():c for c in imp.columns}
            type_present="type" in lower; status_present="status" in lower
            rows=[]
            for _,r in imp.iterrows():
                rows.append((
                    str(r[colmap["club"]]).strip(), str(r[colmap["seizoen"]]).strip(),
                    normalize_type(str(r[colmap["type"]]).strip()) if type_present and pd.notna(r[colmap["type"]]) else "Thuis",
                    str(r[colmap["maat"]]).strip(), str(r[colmap["bedrukking"]]).strip(), str(r[colmap["serienummer"]]).strip(),
                    "Ja" if str(r[colmap["zelf_gekocht"]]).strip().lower() in ("ja","yes","true","1") else "Nee",
                    float(r[colmap["aanschaf_prijs"]]), "" if pd.isna(r[colmap["extra_info"]]) else str(r[colmap["extra_info"]]).strip(),
                    "Actief" if (not status_present or pd.isna(r[colmap["status"]])) else str(r[colmap["status"]]).strip(), datetime.utcnow().isoformat()
                ))
            executemany("""INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,status,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""", rows)
            st.success(f"{len(rows)} rijen geïmporteerd.")
        except Exception as e:
            st.error(f"Import mislukt: {e}")
    st.markdown("---")
    st.subheader("Wenslijst export/import")
    dfw2 = load_df("SELECT * FROM wishlist")
    if not dfw2.empty:
        wcsv = dfw2[["club","seizoen","type","opmerking"]].to_csv(index=False).encode("utf-8")
        st.download_button("Exporteer wenslijst (CSV)", wcsv, "wenslijst_export.csv", "text/csv")
    else:
        st.info("Nog geen wenslijst om te exporteren.")
    mode = st.radio("Importmodus", ["Toevoegen (duplicaten overslaan)","Vervangen (eerst leeg)"], horizontal=True)
    up_w = st.file_uploader("Importeer wenslijst-CSV (kolommen: club,seizoen,type(optional),opmerking)", type=["csv"])
    if up_w is not None:
        try:
            impw=pd.read_csv(up_w); col={c.lower().strip():c for c in impw.columns}
            def pick(*n):
                for x in n:
                    if x in col: return col[x]
                return None
            cc=pick("club","team"); cs=pick("seizoen","season"); ct=pick("type","kit"); co=pick("opmerking","notes","remark")
            if not cc or not cs: st.error("Kolommen 'club' en 'seizoen' zijn verplicht."); st.stop()
            rows=[]
            for _,r in impw.iterrows():
                t=None
                if ct and pd.notna(r[ct]): t=normalize_type(r[ct])
                opm=None
                if co and pd.notna(r[co]): opm=str(r[co]).strip()
                rows.append((str(r[cc]).strip(), str(r[cs]).strip(), t, opm))
            if mode.startswith("Vervangen"): execute("DELETE FROM wishlist")
            if rows: executemany("INSERT INTO wishlist (club,seizoen,type,opmerking) VALUES (?,?,?,?)", rows)
            st.success(f"{len(rows)} wens(en) geïmporteerd.")
        except Exception as e:
            st.error(f"Import mislukt: {e}")

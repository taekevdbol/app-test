
import streamlit as st
import sqlite3
import pandas as pd
from contextlib import closing
from datetime import datetime, date
import os, base64, json, io
from PIL import Image

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
from st_aggrid.shared import JsCode

DB_PATH = "shirts.db"
IMAGES_DIR = "images"
MAX_W, MAX_H = 2000, 2000
JPEG_QUALITY = 90

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

def _resize_and_save(image_bytes, dest_path):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((MAX_W, MAX_H), Image.LANCZOS)
    img.save(dest_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)

def save_uploaded_file(uploaded_file):
    if not uploaded_file: return None
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe = "".join(ch for ch in uploaded_file.name if ch.isalnum() or ch in ("-","_","."," ")).strip().replace(" ","_")
    out = os.path.join(IMAGES_DIR, f"{ts}_{safe.rsplit('.',1)[0]}.jpg")
    _resize_and_save(uploaded_file.getbuffer(), out)
    return out

def to_data_uri(path):
    if not path or not os.path.exists(path): return None
    with open(path, "rb") as f: b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"

def get_photo_data_uris(shirt_id:int):
    rows = load_df("SELECT path FROM photos WHERE shirt_id=? ORDER BY id ASC", (int(shirt_id),))
    if rows.empty: return []
    return [to_data_uri(p) for p in rows["path"].tolist() if to_data_uri(p)]

def normalize_type(val):
    if val is None or (isinstance(val, float) and pd.isna(val)): return None
    s = str(val).strip().lower()
    m = {"thuis":"Thuis","home":"Thuis","uit":"Uit","away":"Uit","derde":"Derde","third":"Derde","3e":"Derde","keepers":"Keepers","gk":"Keepers","special":"Special"}
    return m.get(s, s.title())

def parse_season_start(s):
    if not s: return -1
    s = str(s); digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits[:4]) if len(digits)>=4 else -1

def get_setting(key, default=None):
    df = load_df("SELECT value FROM settings WHERE key=?", (key,))
    if df.empty: return default
    return df.iloc[0]["value"]

def set_setting(key,val):
    if get_setting(key) is None: execute("INSERT INTO settings (key,value) VALUES (?,?)",(key,str(val)))
    else: execute("UPDATE settings SET value=? WHERE key=?", (str(val), key))

# UI
st.set_page_config(page_title="Shirt Collectie", page_icon="🧺", layout="wide")
init_db()
st.title("⚽ Shirt Collectie — v5.2.3 (fotobeheer-blok verwijderd)")

TYPES = ["Thuis","Uit","Derde","Keepers","Special"]
MAATEN = ["Kids XS","Kids S","Kids M","Kids L","XS","S","M","L","XL","XXL","XXXL"]

tabs = st.tabs(["➕ Shirt toevoegen","📚 Collectie (klik rij/thumbnail)","⭐ Wenslijst & Missende shirts","💸 Verkoop & Budget","⬇️⬆️ Import / Export"])

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

with tabs[1]:
    st.subheader("📚 Alle shirts — klik rij/thumbnail voor grote foto")
    fallback = st.toggle("Veilige fotomodus (fallback)", value=False)
    df = load_df("SELECT * FROM shirts")
    if df.empty:
        st.info("Nog geen shirts.")
    else:
        f1,f2,f3,f4,f5,f6 = st.columns(6)
        m = pd.Series(True, index=df.index)
        v1=f1.text_input("Filter club");    m &= df["club"].str.contains(v1, case=False, na=False) if v1 else m
        v2=f2.text_input("Filter seizoen"); m &= df["seizoen"].str.contains(v2, case=False, na=False) if v2 else m
        v3=f3.multiselect("Type", TYPES);   m &= df["type"].isin(v3) if v3 else m
        v4=f4.multiselect("Maat", sorted(df["maat"].unique().tolist())); m &= df["maat"].isin(v4) if v4 else m
        v5=f5.multiselect("Zelf gekocht", ["Ja","Nee"]); m &= df["zelf_gekocht"].isin(v5) if v5 else m
        v6=f6.multiselect("Status", ["Actief","Verkocht"], default=["Actief","Verkocht"]); m &= df["status"].isin(v6) if v6 else m

        dfv = df[m].copy(); dfv["seizoen_start"]=dfv["seizoen"].apply(parse_season_start)
        dfv.sort_values(by=["status","club","seizoen_start","type"], ascending=[True,True,False,True], inplace=True)
        dfv.drop(columns=["seizoen_start"], inplace=True)

        thumbs=[]; galleries=[]
        for _,r in dfv.iterrows():
            imgs = get_photo_data_uris(int(r["id"]))
            thumbs.append(imgs[0] if imgs else None); galleries.append(json.dumps(imgs))
        dfv["thumb"]=thumbs; dfv["gallery_urls"]=galleries

        show = ["thumb","id","club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","gallery_urls"]
        gdf = dfv[show].copy()

        go = GridOptionsBuilder.from_dataframe(gdf)
        go.configure_selection("single")
        if not fallback:
            go.configure_grid_options(domLayout='autoHeight', masterDetail=True, detailRowAutoHeight=True, detailRowHeight=700)
        else:
            go.configure_grid_options(domLayout='autoHeight')

        thumb = JsCode("""
        class ThumbRenderer {
          init(p){
            this.eGui=document.createElement('div');
            const u=p.value;
            if(u){ this.eGui.innerHTML=`<img src="${u}" style="height:56px;border-radius:6px;cursor:pointer">`; this.eGui.addEventListener('click',()=>{ if(p.node.master) p.node.setExpanded(!p.node.expanded); }); }
            else{ this.eGui.innerHTML=`<div style="height:56px;display:flex;align-items:center;color:#bbb">(geen foto)</div>`; }
          }
          getGui(){ return this.eGui; }
        }""")
        go.configure_column("thumb", headerName="Foto", width=120, pinned="left", suppressMenu=True, sortable=False, filter=False, resizable=False, cellRenderer=thumb)
        go.configure_column("gallery_urls", hide=True)

        if not fallback:
            on_click = JsCode("""
            function(p){
              p.api.forEachNode(n=>{ if(n.master && n!==p.node) n.setExpanded(false); });
              if(p.node.master) p.node.setExpanded(!p.node.expanded);
            }""")
            go.configure_grid_options(onRowClicked=on_click)

            detail = JsCode("""
            class DetailCellRenderer{
              init(p){
                this.eGui=document.createElement('div'); this.eGui.style.padding='10px';
                const gal = JSON.parse(p.data.gallery_urls||"[]"); const first = gal.length?gal[0]:null;
                const wrap=document.createElement('div'); wrap.style.display='grid'; wrap.style.gridTemplateColumns='1fr'; wrap.style.rowGap='10px';

                const controls=document.createElement('div'); controls.style.display='flex'; controls.style.justifyContent='space-between'; controls.style.gap='8px';
                const left=document.createElement('div'); left.style.display='flex'; left.style.gap='8px';
                const mk=(t)=>{const b=document.createElement('button'); b.textContent=t; b.style.padding='4px 8px'; b.style.borderRadius='6px'; b.style.border='1px solid #444'; b.style.background='#222'; b.style.color='#ddd'; b.style.cursor='pointer'; return b;};
                const bS=mk('Klein'), bM=mk('Groot'), bL=mk('XL'); left.appendChild(bS); left.appendChild(bM); left.appendChild(bL);
                const right=document.createElement('div'); const bFS=mk('Volledig scherm'); right.appendChild(bFS);
                controls.appendChild(left); controls.appendChild(right);

                const frame=document.createElement('div');
                frame.style.height='60vh'; frame.style.overflow='hidden'; frame.style.display='flex'; frame.style.alignItems='center'; frame.style.justifyContent='center'; frame.style.borderRadius='12px'; frame.style.background='#111';
                const big=document.createElement('img'); big.style.maxWidth='100%'; big.style.maxHeight='100%'; big.style.objectFit='contain'; if(first) big.src=first;
                bS.onclick=()=>{frame.style.height='40vh'}; bM.onclick=()=>{frame.style.height='60vh'}; bL.onclick=()=>{frame.style.height='85vh'};

                const overlay=document.createElement('div'); overlay.style.position='fixed'; overlay.style.left='0'; overlay.style.top='0'; overlay.style.width='100vw'; overlay.style.height='100vh'; overlay.style.background='rgba(0,0,0,0.95)'; overlay.style.display='none'; overlay.style.zIndex='99999'; overlay.style.alignItems='center'; overlay.style.justifyContent='center';
                const fs=document.createElement('img'); fs.style.maxWidth='95vw'; fs.style.maxHeight='95vh'; fs.style.objectFit='contain'; overlay.appendChild(fs);
                overlay.addEventListener('click',()=>{overlay.style.display='none'}); window.addEventListener('keydown',(e)=>{if(e.key==='Escape') overlay.style.display='none'});
                this.eGui.appendChild(overlay); bFS.onclick=()=>{fs.src=big.src; overlay.style.display='flex'};

                frame.appendChild(big);

                const strip=document.createElement('div'); strip.style.display='flex'; strip.style.flexWrap='wrap'; strip.style.gap='8px';
                gal.forEach(u=>{ const t=document.createElement('img'); t.src=u; t.style.height='64px'; t.style.borderRadius='8px'; t.style.cursor='pointer'; t.onclick=()=>{big.src=u}; strip.appendChild(t); });

                if(!first){ this.eGui.innerHTML=`<div style="color:#bbb">Geen foto's bij dit shirt.</div>`; }
                else{ wrap.appendChild(controls); wrap.appendChild(frame); if(gal.length>1) wrap.appendChild(strip); this.eGui.appendChild(wrap); }
              }
              getGui(){return this.eGui;}
            }""")
            go.configure_grid_options(detailCellRenderer=detail)

        grid = AgGrid(
            gdf, gridOptions=go.build(),
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            fit_columns_on_grid_load=True, allow_unsafe_jscode=True, enable_enterprise_modules=True
        )

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
    st.dataframe(dfw, use_container_width=True, hide_index=True) if not dfw.empty else st.info("Nog geen items.")
    st.markdown("---")
    st.subheader("🧩 Missende shirts")
    df_sh = load_df("SELECT club,seizoen,type FROM shirts WHERE status='Actief'")
    if dfw.empty: st.info("Vul of importeer eerst je wenslijst.")
    else:
        if df_sh.empty: missing=dfw.copy()
        else:
            dfw_ = dfw.copy(); dfw_["type"]=dfw_["type"].fillna("").apply(normalize_type).fillna("")
            dfw_["key"]=dfw_["club"].str.lower().str.strip()+"||"+dfw_["seizoen"].astype(str).str.lower().str.strip()+"||"+dfw_["type"].str.lower().str.strip()
            dsh = df_sh.copy(); dsh["type"]=dsh["type"].fillna("").apply(normalize_type).fillna("")
            dsh["key"]=dsh["club"].str.lower().str.strip()+"||"+dsh["seizoen"].astype(str).str.lower().str.strip()+"||"+dsh["type"].str.lower().str.strip()
            dsh2 = df_sh.copy(); dsh2["key"]=dsh2["club"].str.lower().str.strip()+"||"+dsh2["seizoen"].astype(str).str.lower().str.strip()+"||"
            exist=set(dsh["key"]).union(set(dsh2["key"])); missing=dfw_[~dfw_["key"].isin(exist)].drop(columns=["key"])
        st.dataframe(missing, use_container_width=True, hide_index=True) if not missing.empty else st.success("Alles aanwezig.")

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

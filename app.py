
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

# ---------- DB ----------
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

# ---------- Helpers ----------
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

def norm_yesno(v):
    s = str(v).strip().lower()
    return "Ja" if s in ("ja","yes","y","true","1") else "Nee"

def norm_status(v):
    s = str(v).strip().lower()
    return "Verkocht" if s in ("verkocht","sold") else "Actief"

def save_uploaded_file(uploaded_file):
    if not uploaded_file: return None
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe = "".join(ch for ch in uploaded_file.name if ch.isalnum() or ch in ("-","_","."," ")).strip().replace(" ","_")
    out = os.path.join(IMAGES_DIR, f"{ts}_{safe}")
    with open(out, "wb") as f: f.write(uploaded_file.getbuffer())
    return out

def remove_from_wishlist_if_present(club:str, seizoen:str, typ:str):
    c = club.strip().lower(); s = seizoen.strip().lower()
    t = normalize_type(typ) or ""
    df = load_df("SELECT id, club, seizoen, type FROM wishlist")
    if df.empty: return 0
    df["_c"]=df["club"].str.strip().str.lower()
    df["_s"]=df["seizoen"].astype(str).str.strip().str.lower()
    df["_t"]=df["type"].fillna("").astype(str).str.strip()
    mask=(df["_c"]==c) & (df["_s"]==s) & ((df["_t"]=="") | (df["_t"].str.lower()==t.lower()))
    ids=df.loc[mask,"id"].tolist()
    if ids:
        q="DELETE FROM wishlist WHERE id IN (%s)" % ",".join("?"*len(ids))
        execute(q, ids)
    return len(ids)

# ---------- UI ----------
st.set_page_config(page_title="Shirt Collectie", page_icon="🧺", layout="wide")
init_db()
st.title("⚽ Shirt Collectie — v5.4.0 (rij verwijderen + opslaan‑knop)")

TYPES = ["Thuis","Uit","Derde","Keepers","Special"]
MAATEN = ["Kids XS","Kids S","Kids M","Kids L","XS","S","M","L","XL","XXL","XXXL"]

tabs = st.tabs(["➕ Shirt toevoegen","📚 Collectie (klik foto & bewerken)","⭐ Wenslijst","💸 Verkoop & Budget","⬇️⬆️ Import / Export"])

# TAB 1
with tabs[0]:
    st.subheader("➕ Nieuw shirt toevoegen (verwijdert automatisch uit wenslijst)")
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
            removed = remove_from_wishlist_if_present(club, seizoen, tsel)
            st.success(f"Shirt toegevoegd. ({removed} wens(en) verwijderd)") if removed else st.success("Shirt toegevoegd.")

# TAB 2
with tabs[1]:
    st.subheader("📚 Collectie — klik foto om te vergroten | **Bewerk modus** + **Opslaan** | **Rij verwijderen**")
    edit_mode = st.toggle("✏️ Bewerk modus", value=False)
    if "confirm_delete_id" not in st.session_state: st.session_state.confirm_delete_id=None

    df = load_df("SELECT * FROM shirts")
    if df.empty:
        st.info("Nog geen shirts.")
    else:
        # Filters
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

        show_cols = ["thumb","id","club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","status","gallery_urls","_expanded"]
        gdf = dfv[show_cols].copy()
        orig_edit = dfv[["id","club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","status"]].copy()

        go = GridOptionsBuilder.from_dataframe(gdf)
        go.configure_selection("single")
        go.configure_grid_options(domLayout='normal')
        # Rijhoogte (kleine vergroting)
        get_row_height = JsCode("""
        function(params){
          if (params && params.data && params.data._expanded){ return 160; }
          return 62;
        }""")
        go.configure_grid_options(getRowHeight=get_row_height)

        # Foto-renderer
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
        go.configure_column("thumb", headerName="Foto", width=180, pinned="left", suppressMenu=True, sortable=False, filter=False, resizable=True, cellRenderer=renderer)
        go.configure_column("gallery_urls", hide=True)
        go.configure_column("_expanded", hide=True)

        # Editable columns (alleen als edit_mode)
        editable_cols = ["club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","status"]
        for col in editable_cols:
            if col == "type":
                go.configure_column(col, editable=edit_mode, cellEditor="agSelectCellEditor", cellEditorParams={"values": TYPES})
            elif col == "zelf_gekocht":
                go.configure_column(col, editable=edit_mode, cellEditor="agSelectCellEditor", cellEditorParams={"values": ["Ja","Nee"]})
            elif col == "status":
                go.configure_column(col, editable=edit_mode, cellEditor="agSelectCellEditor", cellEditorParams={"values": ["Actief","Verkocht"]})
            else:
                go.configure_column(col, editable=edit_mode)

        grid = AgGrid(
            gdf, gridOptions=go.build(),
            update_mode=GridUpdateMode.SELECTION_CHANGED,  # geen auto-save bij VALUE_CHANGED
            data_return_mode=DataReturnMode.AS_INPUT,       # wel alle edits terugkrijgen
            fit_columns_on_grid_load=True, allow_unsafe_jscode=True, enable_enterprise_modules=True,
            height=560
        )

        # Knoppen: Opslaan + Verwijderen
        cbtn1, cbtn2, cbtn3 = st.columns([1,1,6])
        save_clicked = cbtn1.button("💾 Opslaan wijzigingen", disabled=not edit_mode, use_container_width=True)
        del_clicked  = cbtn2.button("🗑️ Verwijder geselecteerde rij", use_container_width=True)

        # Opslaan: vergelijk grid["data"] met originele en schrijf in 1 batch
        if save_clicked:
            new_df = pd.DataFrame(grid["data"])
            if new_df.empty:
                st.info("Geen data om op te slaan.")
            else:
                new_edit = new_df[["id"]+editable_cols].copy()
                updates=0
                for _, nr in new_edit.iterrows():
                    oid = int(nr["id"])
                    orow = orig_edit[orig_edit["id"]==oid]
                    if orow.empty: continue
                    orow = orow.iloc[0].to_dict()
                    delta={}
                    for col in editable_cols:
                        nv = nr[col]
                        if col=="type": nv = normalize_type(nv)
                        if col=="zelf_gekocht": nv = norm_yesno(nv)
                        if col=="status": nv = norm_status(nv)
                        if col=="aanschaf_prijs":
                            try: nv = float(nv)
                            except: nv = orow[col]
                        ov = orow[col]
                        if (pd.isna(nv) and pd.isna(ov)) or (nv==ov):
                            continue
                        delta[col]=nv
                    if delta:
                        sets=", ".join([f"{k}=?" for k in delta.keys()])
                        params=list(delta.values())+[oid]
                        execute(f"UPDATE shirts SET {sets} WHERE id=?", params)
                        updates += 1
                if updates>0:
                    st.success(f"{updates} rij(en) opgeslagen.")
                    st.experimental_rerun()
                else:
                    st.info("Geen wijzigingen gevonden.")

        # Verwijderen
        sel = grid["selected_rows"]
        if del_clicked:
            if not sel:
                st.warning("Selecteer eerst een rij om te verwijderen.")
            else:
                st.session_state.confirm_delete_id = int(sel[0]["id"])

        if st.session_state.confirm_delete_id is not None:
            did = st.session_state.confirm_delete_id
            st.error(f"Rij ID {did} verwijderen? Dit verwijdert ook gekoppelde foto's.", icon="⚠️")
            cc1, cc2 = st.columns([1,5])
            if cc1.button("Ja, definitief verwijderen"):
                # verwijder foto's (records + bestanden)
                dfp = load_df("SELECT id, path FROM photos WHERE shirt_id=?", (did,))
                if not dfp.empty:
                    for _, r in dfp.iterrows():
                        try:
                            if r["path"] and os.path.exists(r["path"]):
                                os.remove(r["path"])
                        except Exception:
                            pass
                    execute("DELETE FROM photos WHERE shirt_id=?", (did,))
                # verwijder eventuele sales records
                execute("DELETE FROM sales WHERE shirt_id=?", (did,))
                # verwijder shirt
                execute("DELETE FROM shirts WHERE id=?", (did,))
                st.session_state.confirm_delete_id = None
                st.success(f"Rij {did} verwijderd.")
                st.experimental_rerun()
            if cc2.button("Nee, annuleren"):
                st.session_state.confirm_delete_id = None
                st.info("Verwijderen geannuleerd.")

        # Foto-acties (kleine thumbnails) — zoals eerder
        if sel:
            rid = int(sel[0]["id"])
            with st.expander("📷 Foto‑acties", expanded=False):
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

# TAB 3 (Wenslijst beknopt weergave)
with tabs[2]:
    st.subheader("⭐ Wenslijst")
    dfw = load_df("SELECT * FROM wishlist")
    if not dfw.empty:
        st.dataframe(dfw, use_container_width=True, hide_index=True)
    else:
        st.info("Nog geen items in de wenslijst.")

# TAB 4 en 5 zoals eerder (verkoop en import/export) — compact gehouden
with tabs[3]:
    st.subheader("💸 Verkoop & Budget")
    df_sales = load_df("SELECT * FROM sales")
    tot = 0.0 if df_sales.empty else float(df_sales["winst"].sum())
    st.metric("Totaal winst", f"€ {tot:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
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
            missing=[rc for rc in required if rc not in lower]
            if missing:
                st.error("Ontbrekende kolommen: " + ", ".join(missing)); st.stop()
            colmap={c.lower().strip():c for c in imp.columns}
            type_present="type" in lower; status_present="status" in lower
            rows=[]
            for _,r in imp.iterrows():
                rows.append((
                    str(r[colmap["club"]]).strip(), str(r[colmap["seizoen"]]).strip(),
                    normalize_type(str(r[colmap["type"]]).strip()) if type_present and pd.notna(r[colmap["type"]]) else "Thuis",
                    str(r[colmap["maat"]]).strip(), str(r[colmap["bedrukking"]]).strip(), str(r[colmap["serienummer"]]).strip(),
                    norm_yesno(r[colmap["zelf_gekocht"]]),
                    float(r[colmap["aanschaf_prijs"]]), "" if pd.isna(r[colmap["extra_info"]]) else str(r[colmap["extra_info"]]).strip(),
                    "Actief" if (not status_present or pd.isna(r[colmap["status"]])) else str(r[colmap["status"]]).strip(), datetime.utcnow().isoformat()
                ))
            executemany("""INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,status,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""", rows)
            st.success(f"{len(rows)} rijen geïmporteerd.")
        except Exception as e:
            st.error(f"Import mislukt: {e}")


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

# ---------------- DB INIT / MIGRATIONS ----------------
def init_db():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        # Shirts
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
        cols = {row[1]: row for row in c.execute("PRAGMA table_info(shirts)").fetchall()}
        if "type" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN type TEXT NOT NULL DEFAULT 'Thuis'")
        if "foto_path" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN foto_path TEXT")
        if "status" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN status TEXT NOT NULL DEFAULT 'Actief'")
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

def get_setting(key, default=None):
    df = load_df("SELECT value FROM settings WHERE key=?", (key,))
    if df.empty:
        return default
    return df.iloc[0]["value"]

def set_setting(key, value):
    if get_setting(key) is None:
        execute("INSERT INTO settings (key, value) VALUES (?,?)", (key, str(value)))
    else:
        execute("UPDATE settings SET value=? WHERE key=?", (str(value), key))

def to_data_uri(path: str):
    if not path or not os.path.exists(path):
        return None
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        mime = "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"

# ---------------- UI ----------------
st.set_page_config(page_title="Shirt Collectie", page_icon="🧺", layout="wide", initial_sidebar_state="collapsed")
init_db()

st.title("⚽ Shirt Collectie — Taeke (v3.8)")

tabs = st.tabs([
    "➕ Shirt toevoegen",
    "📚 Alle shirts (rij-uitklap)",
    "⭐ Wenslijst & Missende shirts",
    "💸 Verkoop & Budget",
    "⬇️⬆️ Import / Export",
])

# ---------------- TAB 1: ADD SHIRT ----------------
with tabs[0]:
    st.subheader("➕ Nieuw shirt toevoegen")
    with st.form("add_shirt_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        club = col1.text_input("Club*", placeholder="Ajax")
        seizoen = col2.text_input("Seizoen*", placeholder="1995/96")
        maat = col3.selectbox("Maat*", MAATEN, index=7)
        colx1, colx2, colx3 = st.columns(3)
        type_sel = colx1.selectbox("Type*", TYPES, index=0)
        bedrukking = colx2.text_input("Bedrukking*", placeholder="#10 Tadic of 'X'")
        serienummer = colx3.text_input("Serienummer*", placeholder="P06358")
        col4, col5 = st.columns(2)
        zelf_gekocht = col4.selectbox("Zelf gekocht*", ["Ja","Nee"])
        aanschaf_prijs = col5.number_input("Aanschaf prijs* (€)", min_value=0.0, step=1.0, format="%.2f")
        extra_info = st.text_area("Extra informatie", placeholder="BNWT, staat, locatie, etc.")
        foto = st.file_uploader("Foto (optioneel) – JPG/PNG", type=["jpg","jpeg","png"])
        submitted = st.form_submit_button("Toevoegen", use_container_width=True)
        if submitted:
            required = [club, seizoen, maat, bedrukking, serienummer, zelf_gekocht, type_sel]
            if any([not x or str(x).strip()=="" for x in required]):
                st.error("Vul alle verplichte velden met * in.")
            else:
                foto_path = save_uploaded_file(foto)
                execute(
                    """INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,foto_path,status,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (club.strip(), seizoen.strip(), type_sel, maat, bedrukking.strip(), serienummer.strip(), zelf_gekocht, float(aanschaf_prijs), extra_info.strip(), foto_path, "Actief", datetime.utcnow().isoformat())
                )
                execute("""DELETE FROM wishlist WHERE LOWER(club)=LOWER(?) AND LOWER(seizoen)=LOWER(?) AND (type IS NULL OR TRIM(type)='' OR LOWER(type)=LOWER(?))""",
                        (club.strip(), seizoen.strip(), type_sel))
                st.success("Shirt toegevoegd en eventueel uit de wenslijst verwijderd. 🎉")

# ---------------- TAB 2: COLLECTION (AG GRID MASTER-DETAIL with toggle column) ----------------
with tabs[1]:
    st.subheader("📚 Alle shirts — uitklap in dezelfde rij")
    df = load_df("SELECT * FROM shirts")
    if df.empty:
        st.info("Nog geen shirts in de database.")
    else:
        # Filters
        f1, f2, f3, f4, f5, f6 = st.columns(6)
        f_club = f1.text_input("Filter op club")
        f_seizoen = f2.text_input("Filter op seizoen")
        f_type = f3.multiselect("Filter op type", TYPES)
        f_maat = f4.multiselect("Filter op maat", sorted(df["maat"].unique().tolist()))
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
        df_view["foto_data"] = df_view["foto_path"].apply(to_data_uri)

        # Build grid options
        show_cols = ["id","club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","foto_data"]
        df_grid = df_view[show_cols].copy()
        df_grid.insert(0, "exp", "")  # toggle col at far left

        go = GridOptionsBuilder.from_dataframe(df_grid)
        go.configure_selection("single", use_checkbox=True)
        go.configure_grid_options(domLayout='autoHeight', masterDetail=True, detailRowAutoHeight=True, detailRowHeight=320)

        # Toggle column with onCellClicked to expand/collapse
        exp_renderer = JsCode("""
        function(params) {
          var icon = params.node.expanded ? '▼ Foto' : '▶ Foto';
          return '<span style="cursor:pointer; color:#87cefa;">' + icon + '</span>';
        }
        """)
        on_click = JsCode("""
        function(e) {
          if (e.column && e.column.getColId() === 'exp') {
            e.node.setExpanded(!e.node.expanded);
          }
        }
        """)
        go.configure_column("exp", headerName="", width=90, pinned="left", suppressMenu=True, sortable=False,
                            filter=False, resizable=False, cellRenderer=exp_renderer)
        # Editable columns
        go.configure_column("type", editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': TYPES})
        go.configure_column("maat", editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': MAATEN})
        go.configure_column("zelf_gekocht", editable=True, cellEditor='agSelectCellEditor', cellEditorParams={'values': ["Ja","Nee"]})
        go.configure_column("aanschaf_prijs", editable=True, type=['numericColumn'], valueFormatter="x.toFixed(2)")
        go.configure_column("bedrukking", editable=True)
        go.configure_column("serienummer", editable=True)
        go.configure_column("extra_info", editable=True)
        # Hide foto_data in master table; only used by detail renderer
        go.configure_column("foto_data", hide=True)

        # Detail renderer using data URI
        go.configure_grid_options(
            getDetailRowData={
                "function": """
                function(params) {
                  var url = params.data.foto_data;
                  var txt = '';
                  if (url && url.length > 0) {
                    txt = '<div style="padding:10px;"><img src="'+url+'" style="max-width:100%;height:auto;border-radius:10px;" /></div>';
                  } else {
                    txt = '<div style="padding:12px;color:#bbb;">Geen foto opgeslagen voor dit shirt.</div>';
                  }
                  params.successCallback([{_html: txt}]);
                }
                """
            },
            detailCellRendererParams={
                "detailGridOptions": {
                    "columnDefs": [
                        {"field":"_html","headerName":"Foto","flex":1,"autoHeight":True,"cellRenderer": "agRichTextCellRenderer"}
                    ],
                    "defaultColDef": {"resizable": True}
                }
            },
            onCellClicked=on_click
        )

        grid = AgGrid(
            df_grid,
            gridOptions=go.build(),
            update_mode=GridUpdateMode.MODEL_CHANGED,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            fit_columns_on_grid_load=True,
            allow_unsafe_jscode=True,
            enable_enterprise_modules=False
        )

        if st.button("💾 Opslaan wijzigingen"):
            updated = grid["data"]
            df_updated = pd.DataFrame(updated).merge(df_view[["id"]], on="id", how="inner")
            changed = 0
            for _, row in df_updated.iterrows():
                orig = df_view[df_view["id"]==row["id"]].iloc[0]
                diffs = {}
                for col in ["club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info"]:
                    if str(row[col]) != str(orig[col]):
                        diffs[col] = row[col]
                if diffs:
                    sets = ", ".join([f"{k}=?" for k in diffs.keys()])
                    params = list(diffs.values()) + [int(row["id"])]
                    execute(f"UPDATE shirts SET {sets} WHERE id=?", params)
                    changed += 1
            st.success(f"{changed} rij(en) bijgewerkt.")

        st.markdown("---")
        st.subheader("📷 Foto bewerken (geselecteerde rij)")
        sel = grid["selected_rows"]
        if not sel:
            st.info("Selecteer eerst een rij met het checkboxje in de tabel.")
        else:
            rid = int(sel[0]["id"])
            cur = df_view[df_view["id"]==rid].iloc[0]
            cur_path = cur["foto_path"]
            if cur_path and os.path.exists(cur_path):
                st.image(cur_path, caption="Huidige foto", use_column_width=True)
            colu1, colu2 = st.columns(2)
            newp = colu1.file_uploader("Nieuwe foto uploaden", type=["jpg","jpeg","png"], key=f"photo_edit_{rid}")
            if colu1.button("📷 Opslaan/vervangen", key=f"btn_save_{rid}"):
                if newp is None:
                    st.warning("Geen bestand gekozen.")
                else:
                    try:
                        if cur_path and os.path.exists(cur_path):
                            os.remove(cur_path)
                    except Exception:
                        pass
                    new_path = save_uploaded_file(newp)
                    execute("UPDATE shirts SET foto_path=? WHERE id=?", (new_path, rid))
                    st.success("Foto opgeslagen.")
                    st.experimental_rerun()
            if cur_path and colu2.button("🗑️ Verwijder foto", key=f"btn_del_{rid}"):
                try:
                    if os.path.exists(cur_path):
                        os.remove(cur_path)
                except Exception:
                    pass
                execute("UPDATE shirts SET foto_path=NULL WHERE id=?", (rid,))
                st.success("Foto verwijderd.")
                st.experimental_rerun()

# ---------------- TAB 3: WISHLIST & MISSING ----------------
with tabs[2]:
    st.subheader("⭐ Wenslijst")
    df_w = load_df("SELECT * FROM wishlist")
    if df_w.empty:
        st.info("Nog geen items in de wenslijst.")
    else:
        st.dataframe(df_w, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("🧹 Opschonen / beheren")
    c1, c2, c3 = st.columns([1.2,1.5,2])
    with c1:
        if st.button("Verwijder duplicaten (wenslijst)"):
            dfw = load_df("SELECT * FROM wishlist")
            if dfw.empty:
                st.info("Wenslijst is al leeg.")
            else:
                dfw["type_norm"] = dfw["type"].apply(normalize_type).fillna("")
                dfw["key"] = dfw["club"].str.lower().str.strip()+"||"+dfw["seizoen"].astype(str).str.lower().str.strip()+"||"+dfw["type_norm"].str.lower().str.strip()
                keep_ids = dfw.drop_duplicates("key", keep="first")["id"].tolist()
                # delete others
                del_ids = dfw[~dfw["id"].isin(keep_ids)]["id"].tolist()
                if del_ids:
                    placeholders = ",".join(["?"]*len(del_ids))
                    execute(f"DELETE FROM wishlist WHERE id IN ({placeholders})", tuple(del_ids))
                st.success(f"Dubbelen verwijderd: {len(del_ids)}")
                st.experimental_rerun()
    with c2:
        confirm = st.text_input("Typ LEEG om alles te verwijderen:", key="wipe_wish")
        if st.button("Leeg wenslijst") and confirm.strip().upper()=="LEEG":
            execute("DELETE FROM wishlist", ())
            st.success("Wenslijst geleegd.")
            st.experimental_rerun()

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
        st.dataframe(missing, use_container_width=True, hide_index=True) if not missing.empty else st.success("Alles van je wenslijst zit al in je actieve collectie.")

# ---------------- TAB 4: SALES & BUDGET ----------------
with tabs[3]:
    st.subheader("💸 Verkoop & Budget")
    col_b1, col_b2, col_b3 = st.columns(3)
    goal = col_b1.number_input("Budgetdoel (€)", min_value=0.0, step=10.0, value=float(get_setting("budget_goal", 0) or 0), format="%.2f")
    if col_b1.button("Opslaan doel"):
        set_setting("budget_goal", goal)
        st.success("Budgetdoel opgeslagen.")
    df_sales = load_df("SELECT * FROM sales")
    total_profit = 0.0 if df_sales.empty else float(df_sales["winst"].sum())
    st.metric("Totaal gerealiseerde winst", f"€ {total_profit:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

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
                st.experimental_rerun()

# ---------------- TAB 5: IMPORT / EXPORT ----------------
with tabs[4]:
    st.subheader("⬇️⬆️ Import / Export")

    col1, col2 = st.columns(2)

    # Export collection
    df_all = load_df("SELECT * FROM shirts")
    if not df_all.empty:
        export_cols = ["club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","foto_path","status"]
        csv = df_all[export_cols].to_csv(index=False).encode("utf-8")
        col1.download_button("Exporteer collectie (CSV)", csv, "shirts_export.csv", "text/csv")
    else:
        col1.info("Nog geen collectie om te exporteren.")

    # Import collection
    uploaded = col2.file_uploader("Importeer collectie-CSV (kolommen: club,seizoen,type(optional),maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info)", type=["csv"], key="csv_imp_col")
    if uploaded is not None:
        try:
            imp = pd.read_csv(uploaded)
            lower_cols = [c.lower().strip() for c in imp.columns]
            required = ["club","seizoen","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info"]
            for rc in required:
                if rc not in lower_cols:
                    st.error(f"Kolom '{rc}' ontbreekt in de CSV.")
                    st.stop()
            type_present = "type" in lower_cols
            status_present = "status" in lower_cols
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
                    None,
                    status_present and str(r[colmap["status"]]).strip() or "Actief",
                    datetime.utcnow().isoformat(),
                ))
            executemany("""INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,foto_path,status,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
            st.success(f"{len(rows)} rijen geïmporteerd in collectie.")
        except Exception as e:
            st.error(f"Import mislukt: {e}")

    st.markdown("---")
    st.subheader("Wenslijst export/import")

    # Export wishlist
    df_w = load_df("SELECT * FROM wishlist")
    if not df_w.empty:
        wcsv = df_w[["club","seizoen","type","opmerking"]].to_csv(index=False).encode("utf-8")
        st.download_button("Exporteer wenslijst (CSV)", wcsv, "wenslijst_export.csv", "text/csv")
    else:
        st.info("Nog geen wenslijst om te exporteren.")

    st.markdown("**Importopties voor wenslijst**")
    mode = st.radio("Kies importmodus", ["Toevoegen (sla duplicaten over)", "Vervangen (wenslijst eerst leeg)"], horizontal=True)
    up_w = st.file_uploader("Importeer wenslijst-CSV (kolommen: club,seizoen,type(optional),opmerking)", type=["csv"], key="csv_imp_wish")
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
                st.error("Kolommen 'club' en 'seizoen' zijn verplicht.")
                st.stop()

            rows = []
            for _, r in impw.iterrows():
                t = None
                if col_type and pd.notna(r[col_type]):
                    t = normalize_type(r[col_type])
                opm = None
                if col_opm and pd.notna(r[col_opm]):
                    opm = str(r[col_opm]).strip()
                rows.append((
                    str(r[col_club]).strip(),
                    str(r[col_seizoen]).strip(),
                    t,
                    opm,
                ))

            if mode.startswith("Vervangen"):
                execute("DELETE FROM wishlist", ())

            # Deduplicate during import
            existing = load_df("SELECT club,seizoen,type FROM wishlist")
            existing["type"] = existing["type"].apply(normalize_type).fillna("")
            existing["key"] = existing["club"].str.lower().str.strip()+"||"+existing["seizoen"].astype(str).str.lower().str.strip()+"||"+existing["type"].str.lower().str.strip()
            exist_keys = set(existing["key"].tolist())

            to_insert = []
            for club, seizoen, t, opm in rows:
                t_norm = normalize_type(t) or ""
                key = club.lower().strip()+"||"+str(seizoen).lower().strip()+"||"+t_norm.lower().strip()
                if key in exist_keys:
                    continue
                exist_keys.add(key)
                to_insert.append((club, seizoen, t if t_norm!="" else None, opm))

            if to_insert:
                executemany("INSERT INTO wishlist (club,seizoen,type,opmerking) VALUES (?,?,?,?)", to_insert)
            st.success(f"{len(to_insert)} wens(en) geïmporteerd.")
        except Exception as e:
            st.error(f"Import mislukt: {e}")

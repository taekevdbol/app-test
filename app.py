
import streamlit as st
import sqlite3
import pandas as pd
from contextlib import closing
from datetime import datetime, date
import os

DB_PATH = "shirts.db"
IMAGES_DIR = "images"

# ---------------- DB INIT / MIGRATIONS ----------------
def init_db():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        # Shirts table
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
        # Migrations for existing DBs
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
def parse_season_start(season_text: str) -> int:
    if not season_text:
        return -1
    s = season_text.strip()
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

# ---------------- UI SETUP ----------------
st.set_page_config(page_title="Shirt Collectie", page_icon="🧺", layout="wide", initial_sidebar_state="collapsed")
init_db()

st.title("⚽ Shirt Collectie — Taeke (v3.2)")

tabs = st.tabs([
    "➕ Shirt toevoegen",
    "📚 Alle shirts",
    "⭐ Wenslijst & Missende shirts",
    "💸 Verkoop & Budget",
    "⬇️⬆️ Import / Export",
    "ℹ️ Uitleg"
])

TYPES = ["Thuis","Uit","Derde","Keepers","Special"]
MAATEN = ["Kids XS","Kids S","Kids M","Kids L","XS","S","M","L","XL","XXL","XXXL"]

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

# ---------------- TAB 2: COLLECTION (INLINE EDIT) ----------------
with tabs[1]:
    st.subheader("📚 Alle shirts (inline bewerken)")
    df = load_df("SELECT * FROM shirts")
    if df.empty:
        st.info("Nog geen shirts in de database. Voeg je eerste shirt toe op het tabblad **Shirt toevoegen**.")
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
        # Sort for display
        df_view["seizoen_start"] = df_view["seizoen"].apply(parse_season_start)
        df_view.sort_values(by=["status","club","seizoen_start","type"], ascending=[True, True, False, True], inplace=True)
        df_view.drop(columns=["seizoen_start"], inplace=True)

        # Choose columns to edit inline
        edit_cols = ["club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","status"]
        show_cols = ["id"] + edit_cols + ["foto_path","created_at"]

        df_show = df_view[show_cols].copy()

        edited = st.data_editor(
            df_show,
            num_rows="fixed",
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "type": st.column_config.SelectboxColumn("Type", options=TYPES),
                "maat": st.column_config.SelectboxColumn("Maat", options=MAATEN),
                "zelf_gekocht": st.column_config.SelectboxColumn("Zelf gekocht", options=["Ja","Nee"]),
                "status": st.column_config.SelectboxColumn("Status", options=["Actief","Verkocht"]),
                "aanschaf_prijs": st.column_config.NumberColumn("Aanschaf prijs (€)", format="%.2f", step=1.0),
                "foto_path": st.column_config.TextColumn("Foto-pad (alleen-lezen)", disabled=True),
                "created_at": st.column_config.TextColumn("Aangemaakt op", disabled=True),
            }
        )

        if st.button("💾 Opslaan wijzigingen (alle zichtbare rijen)"):
            # Compare edited vs original and persist changes
            changed = 0
            orig_by_id = df_show.set_index("id")
            ed_by_id = edited.set_index("id")
            for row_id, ed_row in ed_by_id.iterrows():
                if row_id not in orig_by_id.index: 
                    continue
                diffs = {}
                for col in edit_cols:
                    old = orig_by_id.loc[row_id, col]
                    new = ed_row[col]
                    # Normalize NaNs
                    if pd.isna(old) and pd.isna(new):
                        continue
                    if (pd.isna(old) and not pd.isna(new)) or (not pd.isna(old) and pd.isna(new)) or (str(old) != str(new)):
                        diffs[col] = new
                if diffs:
                    # Build update query dynamically
                    sets = ", ".join([f"{k}=?" for k in diffs.keys()])
                    params = list(diffs.values()) + [int(row_id)]
                    execute(f"UPDATE shirts SET {sets} WHERE id=?", params)
                    changed += 1
            st.success(f"Wijzigingen opgeslagen voor {changed} rij(en).")

        st.markdown("—")
        with st.expander("🖼️ Foto bijwerken (optioneel)"):
            sel_id = st.number_input("Rij-ID om foto te wijzigen", min_value=0, step=1)
            new_photo = st.file_uploader("Nieuwe foto uploaden (vervangt huidige)", type=["jpg","jpeg","png"], key="row_photo")
            if st.button("📷 Foto opslaan/verwisselen"):
                # Get current foto_path
                if sel_id and (sel_id in df_view["id"].values):
                    current_path = df_view.loc[df_view["id"]==int(sel_id), "foto_path"].values[0]
                    if new_photo is None:
                        st.warning("Geen bestand geselecteerd.")
                    else:
                        # remove old file if exists
                        try:
                            if current_path and os.path.exists(current_path):
                                os.remove(current_path)
                        except Exception:
                            pass
                        new_path = save_uploaded_file(new_photo)
                        execute("UPDATE shirts SET foto_path=? WHERE id=?", (new_path, int(sel_id)))
                        st.success("Foto bijgewerkt.")
                        st.experimental_rerun()
                else:
                    st.warning("Onbekende ID voor huidige filterselectie.")

        with st.expander("🖼️ Toon foto's van gefilterde resultaten"):
            img_df = df_view.dropna(subset=["foto_path"])
            if img_df.empty:
                st.info("Geen foto's beschikbaar voor de huidige selectie.")
            else:
                cols = st.columns(4)
                i = 0
                for _, row in img_df.iterrows():
                    p = row["foto_path"]
                    if p and os.path.exists(p):
                        with cols[i % 4]:
                            st.image(p, caption=f'{row["club"]} {row["seizoen"]} • {row["type"]} • {row["maat"]}', use_column_width=True)
                        i += 1

# ---------------- TAB 3: WISHLIST & MISSING ----------------
with tabs[2]:
    st.subheader("⭐ Wenslijst")
    with st.form("add_wish", clear_on_submit=True):
        wc1, wc2, wc3, wc4 = st.columns([1,1,1,2])
        w_club = wc1.text_input("Club*", placeholder="Ajax")
        w_seizoen = wc2.text_input("Seizoen*", placeholder="1995/96")
        w_type = wc3.selectbox("Type (optioneel)", ["(leeg)","Thuis","Uit","Derde","Keepers","Special"], index=0)
        w_type_val = None if w_type == "(leeg)" else w_type
        w_opm = wc4.text_input("Opmerking", placeholder="Specifieke badge, maat, etc.")
        w_sub = st.form_submit_button("Toevoegen aan wenslijst")
        if w_sub:
            if not w_club or not w_seizoen:
                st.error("Club en Seizoen zijn verplicht.")
            else:
                execute("INSERT INTO wishlist (club,seizoen,type,opmerking) VALUES (?,?,?,?)",
                        (w_club.strip(), w_seizoen.strip(), w_type_val, w_opm.strip()))
                st.success("Toegevoegd aan wenslijst.")

    df_w = load_df("SELECT * FROM wishlist")
    if not df_w.empty:
        st.dataframe(df_w, use_container_width=True, hide_index=True)
        dcol1, dcol2 = st.columns(2)
        del_wish_id = dcol1.number_input("Verwijder wens – ID", min_value=0, step=1)
        if dcol1.button("Verwijder wens"):
            if del_wish_id and int(del_wish_id) in df_w["id"].values:
                execute("DELETE FROM wishlist WHERE id=?", (int(del_wish_id),))
                st.success("Wens verwijderd.")
                st.experimental_rerun()
            else:
                st.warning("Onbekende ID.")
    else:
        st.info("Nog geen items in de wenslijst.")

    st.markdown("---")
    st.subheader("🧩 Missende shirts (nog niet in je collectie)")
    df_sh = load_df("SELECT club,seizoen,type FROM shirts WHERE status='Actief'")
    if df_w.empty:
        st.info("Vul eerst je wenslijst in.")
    else:
        if df_sh.empty:
            missing = df_w.copy()
        else:
            df_w_ = df_w.copy()
            df_w_["type"] = df_w_["type"].fillna("")
            df_w_["key"] = df_w_["club"].str.lower().str.strip() + "||" + df_w_["seizoen"].str.lower().str.strip() + "||" + df_w_["type"].str.lower().str.strip()
            df_sh_ = df_sh.copy()
            df_sh_["type"] = df_sh_["type"].fillna("")
            df_sh_["key"] = df_sh_["club"].str.lower().str.strip() + "||" + df_sh_["seizoen"].str.lower().str.strip() + "||" + df_sh_["type"].str.lower().str.strip()
            df_sh_2 = df_sh.copy()
            df_sh_2["key"] = df_sh_2["club"].str.lower().str.strip() + "||" + df_sh_2["seizoen"].str.lower().str.strip() + "||"
            existing_keys = set(df_sh_["key"]).union(set(df_sh_2["key"]))
            missing = df_w_[~df_w_["key"].isin(existing_keys)].drop(columns=["key"])
        if missing.empty:
            st.success("Mooi! Alles op je wenslijst zit al in je actieve collectie. ✅")
        else:
            st.dataframe(missing, use_container_width=True, hide_index=True)

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
    goal_val = float(get_setting("budget_goal", 0) or 0)
    if goal_val > 0:
        progress = min(1.0, total_profit/goal_val) if goal_val else 0
        st.progress(progress, text=f"Voortgang richting doel (€ {goal_val:,.2f})".replace(",", "X").replace(".", ",").replace("X","."))

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

    st.markdown("---")
    st.subheader("Verkopen overzicht")
    df_sales = load_df("""
        SELECT s.id as sale_id, sh.id as shirt_id, sh.club, sh.seizoen, sh.type, sh.maat, sh.bedrukking,
               sh.aanschaf_prijs, s.verkoop_prijs, s.verkoop_kosten, s.winst, s.verkoop_datum, s.koper, s.opmerking
        FROM sales s JOIN shirts sh ON s.shirt_id = sh.id
        ORDER BY s.verkoop_datum DESC, s.id DESC
    """)
    if df_sales.empty:
        st.info("Nog geen verkopen geregistreerd.")
    else:
        st.dataframe(df_sales, use_container_width=True, hide_index=True)

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
                    str(r[colmap["type"]]).strip() if type_present and pd.notna(r[colmap["type"]]) else "Thuis",
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

    # Import wishlist
    up_w = st.file_uploader("Importeer wenslijst-CSV (kolommen: club,seizoen,type(optional),opmerking)", type=["csv"], key="csv_imp_wish")
    if up_w is not None:
        try:
            impw = pd.read_csv(up_w)
            lower = [c.lower().strip() for c in impw.columns]
            if "club" not in lower or "seizoen" not in lower:
                st.error("Kolommen 'club' en 'seizoen' zijn verplicht.")
                st.stop()
            colmap = {c.lower().strip(): c for c in impw.columns}
            type_present = "type" in lower
            opm_present = "opmerking" in lower
            rows = []
            for _, r in impw.iterrows():
                rows.append((
                    str(r[colmap["club"]]).strip(),
                    str(r[colmap["seizoen"]]).strip(),
                    (str(r[colmap["type"]]).strip() if type_present and pd.notna(r[colmap["type"]]) else None),
                    (str(r[colmap["opmerking"]]).strip() if opm_present and pd.notna(r[colmap["opmerking"]]) else None),
                ))
            executemany("INSERT INTO wishlist (club,seizoen,type,opmerking) VALUES (?,?,?,?)", rows)
            st.success(f"{len(rows)} wens(en) geïmporteerd.")
        except Exception as e:
            st.error(f"Import mislukt: {e}")

# ---------------- TAB 6: HELP ----------------
with tabs[5]:
    st.subheader("Uitleg & Tips (v3.2)")
    st.markdown("""
**Nieuw in v3.2**
- **Inline bewerken**: pas rijen direct aan in **Alle shirts** en klik *💾 Opslaan wijzigingen*.
- **Foto bijwerken per rij** (onder de tabel) zonder door ID-menu's te gaan.

**Overig**
- Wenslijst import/export, verkopen + budget, foto-galerij, en alle filters blijven gewoon werken.
""")

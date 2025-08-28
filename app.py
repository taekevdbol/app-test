
import streamlit as st
import sqlite3
import pandas as pd
from contextlib import closing
from datetime import datetime
import os
import io

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
            foto_path TEXT,
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
        cols = {row[1] for row in c.execute("PRAGMA table_info(shirts)").fetchall()}
        if "type" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN type TEXT NOT NULL DEFAULT 'Thuis'")
        if "foto_path" not in cols:
            c.execute("ALTER TABLE shirts ADD COLUMN foto_path TEXT")
        conn.commit()

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

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

st.set_page_config(page_title="Shirt Collectie", page_icon="🧺", layout="wide", initial_sidebar_state="collapsed")
init_db()

st.title("⚽ Shirt Collectie — Taeke")

tabs = st.tabs(["➕ Shirt toevoegen", "📚 Alle shirts", "⭐ Wenslijst & Missende shirts", "⬇️⬆️ Import / Export", "ℹ️ Uitleg"])

TYPES = ["Thuis","Uit","Derde","Keepers","Special"]
MAATEN = ["Kids XS","Kids S","Kids M","Kids L","XS","S","M","L","XL","XXL","XXXL"]

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
                    """INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,foto_path,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (club.strip(), seizoen.strip(), type_sel, maat, bedrukking.strip(), serienummer.strip(), zelf_gekocht, float(aanschaf_prijs), extra_info.strip(), foto_path, datetime.utcnow().isoformat())
                )
                execute("""DELETE FROM wishlist WHERE LOWER(club)=LOWER(?) AND LOWER(seizoen)=LOWER(?) AND (type IS NULL OR TRIM(type)='' OR LOWER(type)=LOWER(?))""",
                        (club.strip(), seizoen.strip(), type_sel))
                st.success("Shirt toegevoegd en eventueel uit de wenslijst verwijderd. 🎉")

with tabs[1]:
    st.subheader("📚 Alle shirts (collectie)")
    df = load_df("SELECT * FROM shirts")
    if df.empty:
        st.info("Nog geen shirts in de database. Voeg je eerste shirt toe op het tabblad **Shirt toevoegen**.")
    else:
        f1, f2, f3, f4, f5 = st.columns(5)
        f_club = f1.text_input("Filter op club")
        f_seizoen = f2.text_input("Filter op seizoen")
        f_type = f3.multiselect("Filter op type", TYPES)
        f_maat = f4.multiselect("Filter op maat", sorted(df["maat"].unique().tolist()))
        f_zelf = f5.multiselect("Filter op zelf gekocht", ["Ja","Nee"])

        mask = pd.Series(True, index=df.index)
        if f_club:
            mask &= df["club"].str.contains(f_club, case=False, na=False)
        if f_seizoen:
            mask &= df["seizoen"].str.contains(f_seizoen, case=False, na=False)
        if f_type:
            mask &= df["type"].isin(f_type)
        if f_maat:
            mask &= df["maat"].isin(f_maat)
        if f_zelf:
            mask &= df["zelf_gekocht"].isin(f_zelf)
        df_f = df[mask].copy()

        df_f["seizoen_start"] = df_f["seizoen"].apply(parse_season_start)
        df_f.sort_values(by=["club","seizoen_start","type"], ascending=[True, False, True], inplace=True)
        df_f.drop(columns=["seizoen_start"], inplace=True)

        show_cols = ["id","club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","foto_path","created_at"]
        st.dataframe(df_f[show_cols], use_container_width=True, hide_index=True)

        with st.expander("🖼️ Toon foto's van gefilterde resultaten"):
            img_df = df_f.dropna(subset=["foto_path"])
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

        with st.expander("Verwijderen / Bewerken"):
            colA, colB = st.columns(2)
            del_id = colA.number_input("Verwijder shirt met ID", min_value=0, step=1)
            if colA.button("Verwijder", type="primary"):
                if del_id and int(del_id) in df["id"].values:
                    path = df.loc[df["id"]==int(del_id), "foto_path"].values[0]
                    execute("DELETE FROM shirts WHERE id=?", (int(del_id),))
                    try:
                        if path and os.path.exists(path):
                            os.remove(path)
                    except Exception:
                        pass
                    st.success(f"Shirt met ID {int(del_id)} verwijderd.")
                    st.experimental_rerun()
                else:
                    st.warning("Onbekende ID.")

            edit_id = colB.number_input("Bewerk – ID", min_value=0, step=1)
            new_price = colB.number_input("Nieuwe prijs (€)", min_value=0.0, step=1.0, format="%.2f")
            new_info  = colB.text_input("Nieuwe extra info")
            new_type  = colB.selectbox("Nieuw type", ["(geen wijziging)"] + TYPES, index=0)
            new_photo = colB.file_uploader("Nieuwe foto (optioneel) – vervangt bestaande", type=["jpg","jpeg","png"], key="reupload")
            if colB.button("Opslaan wijzigingen"):
                if edit_id and int(edit_id) in df["id"].values:
                    # Current values
                    current = df[df["id"]==int(edit_id)].iloc[0]
                    foto_path = current["foto_path"]
                    update_type = current["type"] if new_type == "(geen wijziging)" else new_type
                    if new_photo is not None:
                        try:
                            if foto_path and os.path.exists(foto_path):
                                os.remove(foto_path)
                        except Exception:
                            pass
                        foto_path = save_uploaded_file(new_photo)
                    execute("UPDATE shirts SET aanschaf_prijs=?, extra_info=?, type=?, foto_path=? WHERE id=?",
                            (float(new_price), new_info, update_type, foto_path, int(edit_id)))
                    st.success("Wijzigingen opgeslagen.")
                    st.experimental_rerun()
                else:
                    st.warning("Onbekende ID.")

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
    df_sh = load_df("SELECT club,seizoen,type FROM shirts")
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
            st.success("Mooi! Alles op je wenslijst zit al in je collectie. ✅")
        else:
            st.dataframe(missing, use_container_width=True, hide_index=True)

with tabs[3]:
    st.subheader("⬇️⬆️ Import / Export")
    col1, col2 = st.columns(2)
    df_all = load_df("SELECT * FROM shirts")
    if not df_all.empty:
        export_cols = ["club","seizoen","type","maat","bedrukking","serienummer","zelf_gekocht","aanschaf_prijs","extra_info","foto_path"]
        csv = df_all[export_cols].to_csv(index=False).encode("utf-8")
        col1.download_button("Exporteer collectie (CSV)", csv, "shirts_export.csv", "text/csv")
    else:
        col1.info("Nog niets te exporteren.")
    uploaded = col2.file_uploader("Importeer CSV (kolommen: club,seizoen,type(optional),maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info)", type=["csv"], key="csv_imp")
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
                    datetime.utcnow().isoformat(),
                ))
            executemany("""INSERT INTO shirts (club,seizoen,type,maat,bedrukking,serienummer,zelf_gekocht,aanschaf_prijs,extra_info,foto_path,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""", rows)
            st.success(f"{len(rows)} rijen geïmporteerd.")
        except Exception as e:
            st.error(f"Import mislukt: {e}")

with tabs[4]:
    st.subheader("Uitleg")
    st.markdown("""
**Nieuw in deze versie**
- **Type** (Thuis/Uit/Derde/Keepers/Special) staat nu bij **Shirt toevoegen** en in het overzicht.
- **Foto uploaden** bij het toevoegen (en vervangen bij bewerken). Foto's worden opgeslagen in de map **images**.
- Wenslijst verwijderen kijkt nu naar **Club + Seizoen** en **Type** (indien ingevuld). Als type op de wenslijst leeg is, verdwijnt het item bij elk type dat je toevoegt.

**Hoe werkt het?**
- Voeg shirts toe via **Shirt toevoegen** — inclusief optionele foto.
- Overzicht filtert en sorteert op Club (A→Z), Seizoen-start (nieuw→oud), Type (A→Z).
- **Wenslijst & Missende**: voeg items toe; als je een match toevoegt, verdwijnt die automatisch uit de wenslijst.
- **Import/Export**: CSV export bevat een `foto_path` kolom; bij import is `type` optioneel (default = Thuis).

**Tip:** Gebruik seizoen notatie `1995/96` of `2009/10` voor perfecte sortering.
""")

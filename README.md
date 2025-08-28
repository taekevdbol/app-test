# Shirt Collectie App v3.2 — inline editing
- Inline edits via `st.data_editor` met selectboxen voor type/maat/status en Ja/Nee.
- Foto per rij bijwerken via uploader.
- Overige functies (wishlist import/export, sales & budget) blijven werken.

## Run lokaal
```
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud
Zet `runtime.txt` met:
```
python-3.12
```

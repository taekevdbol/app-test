# Shirt Collectie App v3.4 — in-rij uitklappen + verborgen kolommen
- In de tabel een kolom **Uitklappen (▶/▼)** per rij; bij ▼ verschijnt onderaan een expander met de foto + uploader.
- Kolommen **Status** en **Aangemaakt op** zijn verborgen in de tabel (filters op status blijven).

## Lokaal
```
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud
Plaats `runtime.txt` met:
```
python-3.12
```

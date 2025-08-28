# Shirt Collectie App v3.3 — thumbnails + per-rij foto-expander
- Foto-thumbnails direct in de tabel via `ImageColumn`.
- Per-rij expander om foto te bekijken/vervangen/verwijderen (geen losse sectie meer).
- Inline tekst-edit blijft aanwezig.

## Lokaal starten
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

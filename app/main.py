from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
import numpy as np
import io
import os
from typing import List, Dict, Optional, Tuple

app = FastAPI(
    title="Stokklukeanalyse API", 
    description="DevOps Project - Michal Kuszynski", 
    version="1.0.1"
)

# Endpoint: /health
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "stokklukeanalyse"}

# Endpoint: /version
@app.get("/version")
def version_check():
    return {"version": "1.0.0"}

def calculate_capability(data: pd.Series, lsl: float, usl: float) -> Tuple[float, float]:
    mean = data.mean()
    sigma = data.std()
    if sigma == 0 or np.isnan(sigma):
        return 0.0, 0.0
    cp = (usl - lsl) / (6 * sigma)
    cpu = (usl - mean) / (3 * sigma)
    cpl = (mean - lsl) / (3 * sigma)
    cpk = min(cpu, cpl)
    return float(cp), float(cpk)

# Endpoint biznesowy: /api/analyze
@app.post("/api/analyze")
async def analyze_data(
    file: UploadFile = File(...),
    target_val: float = Form(100.0),
    lsl: float = Form(50.0),
    usl: float = Form(150.0),
    exclude_outliers: bool = Form(False),
    enable_filter: bool = Form(True),
    filter_col: Optional[str] = Form(None),
    filter_min: Optional[float] = Form(None),
    filter_max: Optional[float] = Form(None),
    col_gap_name: Optional[str] = Form(None),
    col_len_name: Optional[str] = Form(None)
):
    try:
        # Odczytaj zawartość pliku
        contents = await file.read()
        
        # Spróbuj odkodować plik przy użyciu różnych kodowań
        df = None
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                # Spróbuj odczytać jako tab-separated (TSV)
                df = pd.read_csv(io.BytesIO(contents), sep='\t', skipinitialspace=True, encoding=encoding)
                if len(df.columns) < 2:
                    # Spróbuj odczytać jako comma-separated (CSV)
                    df = pd.read_csv(io.BytesIO(contents), sep=',', encoding=encoding)
                break
            except Exception:
                continue

        if df is None or df.empty:
            raise HTTPException(status_code=400, detail="Nie udało się zaimportować pliku. Upewnij się, że plik to CSV lub TXT.")

        # Oczyść nazwy kolumn
        df.columns = df.columns.str.strip()
        all_columns = df.columns.tolist()

        # Wybór kolumn (StoLucka, Längd)
        default_gap = 'StoLucka' if 'StoLucka' in all_columns else all_columns[0]
        default_len = 'Längd' if 'Längd' in all_columns else (all_columns[1] if len(all_columns) > 1 else all_columns[0])
        
        col_gap = col_gap_name if col_gap_name in all_columns else default_gap
        col_len = col_len_name if col_len_name in all_columns else default_len

        # Kolumna do filtrowania (InmDia jako domyślna)
        default_filter = 'InmDia' if 'InmDia' in all_columns else (all_columns[2] if len(all_columns) > 2 else all_columns[0])
        chosen_filter_col = filter_col if filter_col in all_columns else default_filter

        # Podstawowe czyszczenie wierszy z brakującymi danymi w kluczowych kolumnach
        needed_cols = [col_gap, col_len]
        if enable_filter and chosen_filter_col in all_columns:
            needed_cols.append(chosen_filter_col)
            
        df_clean = df[needed_cols].dropna().copy()
        
        # Konwersja do typów numerycznych
        df_clean[col_gap] = pd.to_numeric(df_clean[col_gap], errors='coerce')
        df_clean[col_len] = pd.to_numeric(df_clean[col_len], errors='coerce')
        if enable_filter and chosen_filter_col in all_columns:
            df_clean[chosen_filter_col] = pd.to_numeric(df_clean[chosen_filter_col], errors='coerce')
            
        df_clean = df_clean.dropna()

        if df_clean.empty:
            raise HTTPException(status_code=400, detail="Po oczyszczeniu danych tabela jest pusta. Sprawdź format liczb.")

        # Zapisz informacje o wartościach min/max dla filtra do odesłania do UI
        filter_meta = {"column": chosen_filter_col, "min": 0, "max": 0, "active": False}
        if chosen_filter_col in df.columns:
            filter_series = pd.to_numeric(df[chosen_filter_col], errors='coerce').dropna()
            if not filter_series.empty:
                filter_meta["min"] = float(filter_series.min())
                filter_meta["max"] = float(filter_series.max())

        # Zastosowanie filtra
        df_filtered = df_clean.copy()
        if enable_filter and chosen_filter_col in df_filtered.columns and filter_min is not None and filter_max is not None:
            df_filtered = df_filtered[
                (df_filtered[chosen_filter_col] >= filter_min) & 
                (df_filtered[chosen_filter_col] <= filter_max)
            ]
            filter_meta["active"] = True

        if df_filtered.empty:
            raise HTTPException(status_code=400, detail="Brak danych po zastosowaniu wybranego filtra.")

        # Wyznaczenie anomalii metodą IQR
        Q1 = df_filtered[col_gap].quantile(0.25)
        Q3 = df_filtered[col_gap].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        # Indeksy anomalii przed ewentualnym wykluczeniem
        outliers_low_df = df_filtered[df_filtered[col_gap] < lower_bound]
        outliers_high_df = df_filtered[df_filtered[col_gap] > upper_bound]
        
        outliers_low = outliers_low_df[[col_gap, col_len]].rename(columns={col_gap: "gap", col_len: "length"}).to_dict(orient="records")
        outliers_high = outliers_high_df[[col_gap, col_len]].rename(columns={col_gap: "gap", col_len: "length"}).to_dict(orient="records")
        
        # Wykluczenie anomalii z głównych statystyk, jeśli zaznaczono
        df_final = df_filtered.copy()
        if exclude_outliers:
            df_final = df_filtered[(df_filtered[col_gap] >= lower_bound) & (df_filtered[col_gap] <= upper_bound)]

        if df_final.empty:
            raise HTTPException(status_code=400, detail="Wszystkie wiersze zostały zaklasyfikowane jako anomalie i usunięte.")

        # Oblicz statystyki
        stats = df_final[col_gap].describe()
        mean = float(stats['mean'])
        median = float(df_final[col_gap].median())
        std_dev = float(stats['std'])
        skewness = float(df_final[col_gap].skew())
        kurtosis = float(df_final[col_gap].kurt())
        correlation = float(df_final[col_len].corr(df_final[col_gap])) if not np.isnan(df_final[col_len].corr(df_final[col_gap])) else 0.0

        # Cp i Cpk
        cp, cpk = calculate_capability(df_final[col_gap], lsl, usl)

        # Dane do wykresu Histogramu
        # Podziel dane na 15 kubełków
        counts, bin_edges = np.histogram(df_final[col_gap], bins=15)
        bin_labels = []
        for i in range(len(bin_edges) - 1):
            bin_labels.append(f"{bin_edges[i]:.1f}-{bin_edges[i+1]:.1f}")
        histogram_data = {
            "labels": bin_labels,
            "values": counts.tolist(),
            "edges": bin_edges.tolist()
        }

        # Dane do wykresu przebiegu (Run Chart)
        # Ograniczamy liczbę punktów do max 1000 w celu płynności wykresu w przeglądarce
        if len(df_final) > 1000:
            df_sampled = df_final.sample(n=1000).sort_index()
        else:
            df_sampled = df_final

        run_chart_data = {
            "indices": df_sampled.index.tolist(),
            "gaps": df_sampled[col_gap].tolist()
        }

        # Dane do wykresu korelacji (Scatter Plot)
        scatter_points = []
        for index, row in df_sampled.iterrows():
            scatter_points.append({
                "x": float(row[col_len]),
                "y": float(row[col_gap])
            })
        
        # Wyznaczenie linii trendu (OLS)
        trendline = []
        if len(df_final) > 1:
            try:
                # y = ax + b
                a, b = np.polyfit(df_final[col_len], df_final[col_gap], 1)
                x_min = float(df_final[col_len].min())
                x_max = float(df_final[col_len].max())
                trendline = [
                    {"x": x_min, "y": a * x_min + b},
                    {"x": x_max, "y": a * x_max + b}
                ]
            except Exception:
                pass

        correlation_data = {
            "points": scatter_points,
            "trendline": trendline,
            "coefficient": correlation
        }

        return JSONResponse(content={
            "status": "success",
            "columns": all_columns,
            "config": {
                "col_gap": col_gap,
                "col_len": col_len,
                "col_filter": chosen_filter_col
            },
            "filter_meta": filter_meta,
            "metrics": {
                "count": int(stats['count']),
                "mean": round(mean, 2),
                "median": round(median, 2),
                "std_dev": round(std_dev, 2),
                "skewness": round(skewness, 2) if not np.isnan(skewness) else 0.0,
                "kurtosis": round(kurtosis, 2) if not np.isnan(kurtosis) else 0.0,
                "cp": round(cp, 2) if not np.isnan(cp) else 0.0,
                "cpk": round(cpk, 2) if not np.isnan(cpk) else 0.0
            },
            "outliers": {
                "low_count": len(outliers_low_df),
                "high_count": len(outliers_high_df),
                "total_percentage": round(((len(outliers_low_df) + len(outliers_high_df)) / len(df_clean)) * 100, 2) if len(df_clean) > 0 else 0.0,
                "low_list": outliers_low[:100],  # ograniczenie do 100
                "high_list": outliers_high[:100],
                "lower_bound": round(lower_bound, 2),
                "upper_bound": round(upper_bound, 2)
            },
            "charts": {
                "histogram": histogram_data,
                "run_chart": run_chart_data,
                "correlation": correlation_data
            }
        })
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": str(e)})

# Podłączenie folderu z plikami statycznymi (szablon HTML/CSS/JS)
# Weryfikacja czy folder istnieje
os.makedirs("app/static", exist_ok=True)
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

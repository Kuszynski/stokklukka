from fastapi.testclient import TestClient
import io
import pytest
from app.main import app, calculate_capability
import pandas as pd

client = TestClient(app)

# Test 1: Punkty kontrolne /health
def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "stokklukeanalyse"}

# Test 2: Punkty kontrolne /version
def test_version_check():
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"version": "1.0.0"}

# Test 3: Logika wyliczania zdolności procesu (Cp, Cpk)
def test_calculate_capability():
    # Przygotowanie idealnego rozkładu wokół średniej 100
    data = pd.Series([100, 105, 95, 100, 102, 98, 101, 99, 100, 100])
    lsl = 50.0
    usl = 150.0
    
    cp, cpk = calculate_capability(data, lsl, usl)
    
    # Cp i Cpk powinny być dodatnie i wysokie
    assert cp > 1.0
    assert cpk > 1.0
    # W idealnym rozkładzie symetrycznym wokół targetu Cp ~= Cpk
    assert abs(cp - cpk) < 0.2

# Test 4: Walidacja API analizy biznesowej (/api/analyze) z mockowym plikiem CSV
def test_analyze_endpoint():
    # Przygotowanie fikcyjnego pliku CSV w pamięci
    # StoLucka (gaps), Längd (length), InmDia (diameter)
    csv_data = (
        "StoLucka\tLängd\tInmDia\n"
        "100\t400\t20\n"
        "102\t410\t22\n"
        "98\t390\t19\n"
        "105\t420\t25\n"
        "95\t380\t18\n"
        "150\t450\t35\n"  # potencjalny wysoki outlier
        "50\t350\t12\n"   # potencjalny niski outlier
        "100\t400\t20\n"
        "100\t400\t20\n"
        "100\t400\t20\n"
    )
    
    file_bytes = csv_data.encode("utf-8")
    
    # Wywołanie endpointu API z przesyłaniem pliku
    response = client.post(
        "/api/analyze",
        files={"file": ("test_snap.txt", io.BytesIO(file_bytes), "text/plain")},
        data={
            "target_val": 100.0,
            "lsl": 60.0,
            "usl": 140.0,
            "exclude_outliers": False,
            "enable_filter": True,
            "filter_col": "InmDia",
            "filter_min": 10.0,
            "filter_max": 40.0
        }
    )
    
    assert response.status_code == 200
    result = response.json()
    
    assert result["status"] == "success"
    assert "metrics" in result
    assert result["metrics"]["count"] == 10
    assert result["metrics"]["mean"] == 100.0
    assert "outliers" in result
    assert "charts" in result
    assert len(result["columns"]) == 3

// Logika frontendu - Stokklukeanalyse

let currentFile = null;
let charts = {
    histogram: null,
    run: null,
    scatter: null
};

// Funkcja pomocnicza do pobierania wersji
async function fetchVersion() {
    try {
        const res = await fetch('/version');
        const data = await res.json();
        document.getElementById('app-version-badge').innerText = `API: v${data.version}`;
    } catch (e) {
        console.error('Błąd pobierania wersji API', e);
    }
}

// Inicjalizacja po załadowaniu strony
document.addEventListener('DOMContentLoaded', () => {
    fetchVersion();

    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const btnAnalyze = document.getElementById('btnAnalyze');

    // Obsługa Drag & Drop
    dropzone.addEventListener('click', () => fileInput.click());
    
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragenter', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    // Przycisk "Analizuj"
    btnAnalyze.addEventListener('click', () => {
        if (currentFile) {
            runAnalysis();
        }
    });

    // Kontrola zakładek wykresów
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            tabButtons.forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            const tabId = btn.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
        });
    });

    // Obsługa checkboxa filtra
    const enableFilter = document.getElementById('enableFilterCheckbox');
    const filterDetails = document.getElementById('filter-details');
    enableFilter.addEventListener('change', (e) => {
        if (e.target.checked) {
            filterDetails.classList.remove('hidden');
        } else {
            filterDetails.classList.add('hidden');
        }
    });
});

// Obsługa wyboru pliku
function handleFileSelect(file) {
    currentFile = file;
    const statusDiv = document.getElementById('file-status');
    statusDiv.classList.remove('hidden', 'error');
    statusDiv.innerHTML = `<strong>Wybrany plik:</strong> ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    
    // Odblokowanie przycisku i przesłanie wstępne w celu zaczytania kolumn
    document.getElementById('btnAnalyze').disabled = false;
    
    // Uruchomienie wstępnej analizy do zaczytania struktury pliku
    initialParse();
}

// Wstępny import danych w celu pobrania nazw kolumn i przedziału filtra
async function initialParse() {
    if (!currentFile) return;

    showLoader(true);
    const formData = new FormData();
    formData.append('file', currentFile);
    formData.append('target_val', document.getElementById('targetInput').value);
    formData.append('lsl', document.getElementById('lslInput').value);
    formData.append('usl', document.getElementById('uslInput').value);
    formData.append('exclude_outliers', document.getElementById('excludeOutliersCheckbox').checked);
    formData.append('enable_filter', false); // Wyłączamy filtr przy pierwszym parsu w celu pobrania całego zakresu

    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        showLoader(false);

        if (data.status === 'success') {
            populateColumnsConfig(data);
            runAnalysis(); // Uruchom właściwą analizę
        } else {
            showError(data.message || 'Wystąpił błąd podczas odczytu struktury pliku.');
        }
    } catch (e) {
        showLoader(false);
        showError('Nie udało się połączyć z serwerem API.');
    }
}

// Wypełnianie selectów kolumnami i ustawienie domyślnych wartości
function populateColumnsConfig(data) {
    const colGapSelect = document.getElementById('colGapSelect');
    const colLenSelect = document.getElementById('colLenSelect');
    const colFilterSelect = document.getElementById('colFilterSelect');

    colGapSelect.innerHTML = '';
    colLenSelect.innerHTML = '';
    colFilterSelect.innerHTML = '';

    data.columns.forEach(col => {
        const opt1 = new Option(col, col);
        const opt2 = new Option(col, col);
        const opt3 = new Option(col, col);
        colGapSelect.add(opt1);
        colLenSelect.add(opt2);
        colFilterSelect.add(opt3);
    });

    // Ustawienie wartości domyślnych odesłanych z backendu
    colGapSelect.value = data.config.col_gap;
    colLenSelect.value = data.config.col_len;
    colFilterSelect.value = data.config.col_filter;

    // Inicjalizacja zakresu filtrów
    document.getElementById('filter-col-name').innerText = data.filter_meta.column;
    
    const sliderMin = document.getElementById('filterRangeMin');
    const sliderMax = document.getElementById('filterRangeMax');
    
    const minVal = Math.floor(data.filter_meta.min);
    const maxVal = Math.ceil(data.filter_meta.max);
    
    sliderMin.min = minVal;
    sliderMin.max = maxVal;
    sliderMin.value = minVal;
    
    sliderMax.min = minVal;
    sliderMax.max = maxVal;
    sliderMax.value = maxVal;

    document.getElementById('range-val-min').innerText = minVal;
    document.getElementById('range-val-max').innerText = maxVal;

    // Zdarzenia suwaków dla płynnej interakcji
    sliderMin.oninput = function() {
        if (parseFloat(this.value) > parseFloat(sliderMax.value)) {
            this.value = sliderMax.value;
        }
        document.getElementById('range-val-min').innerText = this.value;
    };

    sliderMax.oninput = function() {
        if (parseFloat(this.value) < parseFloat(sliderMin.value)) {
            this.value = sliderMin.value;
        }
        document.getElementById('range-val-max').innerText = this.value;
    };

    // Pokazanie sekcji konfiguracyjnych
    document.getElementById('config-section').classList.remove('hidden');
    document.getElementById('filter-section').classList.remove('hidden');
}

// Właściwa analiza danych
async function runAnalysis() {
    if (!currentFile) return;

    showLoader(true);

    const targetVal = parseFloat(document.getElementById('targetInput').value);
    const lsl = parseFloat(document.getElementById('lslInput').value);
    const usl = parseFloat(document.getElementById('uslInput').value);
    const excludeOutliers = document.getElementById('excludeOutliersCheckbox').checked;
    
    const enableFilter = document.getElementById('enableFilterCheckbox').checked;
    const filterCol = document.getElementById('colFilterSelect').value;
    const filterMin = parseFloat(document.getElementById('filterRangeMin').value);
    const filterMax = parseFloat(document.getElementById('filterRangeMax').value);
    
    const colGapName = document.getElementById('colGapSelect').value;
    const colLenName = document.getElementById('colLenSelect').value;

    const formData = new FormData();
    formData.append('file', currentFile);
    formData.append('target_val', targetVal);
    formData.append('lsl', lsl);
    formData.append('usl', usl);
    formData.append('exclude_outliers', excludeOutliers);
    formData.append('enable_filter', enableFilter);
    formData.append('filter_col', filterCol);
    formData.append('filter_min', filterMin);
    formData.append('filter_max', filterMax);
    formData.append('col_gap_name', colGapName);
    formData.append('col_len_name', colLenName);

    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        showLoader(false);

        if (data.status === 'success') {
            renderDashboard(data, targetVal, lsl, usl);
        } else {
            showError(data.message || 'Wystąpił błąd analizy danych.');
        }
    } catch (e) {
        showLoader(false);
        showError('Błąd komunikacji z serwerem.');
    }
}

// Renderowanie całego pulpitów sterowania
function renderDashboard(data, targetVal, lsl, usl) {
    // Ukryj stan pusty, pokaż dashboard
    document.getElementById('no-data-view').classList.add('hidden');
    document.getElementById('dashboard-view').classList.remove('hidden');

    // Aktualizacja wskaźników tekstowych
    document.getElementById('metric-count').innerText = data.metrics.count;
    document.getElementById('metric-mean').innerText = data.metrics.mean;
    document.getElementById('metric-median').innerText = data.metrics.median;
    document.getElementById('metric-std').innerText = data.metrics.std_dev;
    
    document.getElementById('metric-cp').innerText = data.metrics.cp;
    document.getElementById('metric-cpk').innerText = data.metrics.cpk;
    document.getElementById('metric-skew').innerText = data.metrics.skewness;
    document.getElementById('metric-kurt').innerText = data.metrics.kurtosis;

    // Stylizacja kart Cp/Cpk na bazie wartości
    styleCapabilityCard('card-cp', data.metrics.cp);
    styleCapabilityCard('card-cpk', data.metrics.cpk);

    // Sekcja anomalii
    document.getElementById('anomaly-high-count').innerText = data.outliers.high_count;
    document.getElementById('anomaly-low-count').innerText = data.outliers.low_count;
    document.getElementById('anomaly-total-pct').innerText = `${data.outliers.total_percentage}%`;
    document.getElementById('anomaly-high-bound').innerText = `> ${data.outliers.upper_bound} cm`;
    document.getElementById('anomaly-low-bound').innerText = `< ${data.outliers.lower_bound} cm`;

    // Wyświetlanie alertu o anomaliach
    const alertBox = document.getElementById('outliers-alert');
    const totalOutliers = data.outliers.high_count + data.outliers.low_count;
    if (totalOutliers > 0) {
        alertBox.classList.remove('hidden');
        document.getElementById('outliers-alert-text').innerHTML = 
            `IQR zidentyfikował <strong>${totalOutliers} anomalii</strong> (${data.outliers.total_percentage}% wszystkich kłód). Wpływają one negatywnie na wskaźnik Cpk.`;
    } else {
        alertBox.classList.add('hidden');
    }

    // Uzupełnienie tabel anomalii
    populateOutliersTable('high-outliers-table', data.outliers.high_list, 'Wysokie anomalie nie wystąpiły');
    populateOutliersTable('low-outliers-table', data.outliers.low_list, 'Niskie anomalie nie wystąpiły');

    // Wykresy
    renderHistogram(data.charts.histogram, targetVal, lsl, usl);
    renderRunChart(data.charts.run_chart, targetVal, lsl, usl);
    renderCorrelationChart(data.charts.correlation);

    // Wygenerowanie porad Black Belt
    generateLeanTips(data.metrics.cpk, data.metrics.std_dev, data.metrics.mean, targetVal, data.metrics.kurtosis, data.metrics.skewness);
}

// Kolorowanie kart Cp/Cpk na bazie progu Six Sigma
function styleCapabilityCard(cardId, value) {
    const card = document.getElementById(cardId);
    card.classList.remove('pass', 'fail');
    if (value >= 1.33) {
        card.classList.add('pass');
    } else if (value < 1.00) {
        card.classList.add('fail');
    }
}

// Uzupełnianie tabeli
function populateOutliersTable(tableId, list, emptyMsg) {
    const tbody = document.getElementById(tableId);
    tbody.innerHTML = '';
    
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" class="no-outliers">${emptyMsg}</td></tr>`;
        return;
    }

    list.forEach((row, i) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>#${i + 1}</td>
            <td style="color: var(--color-danger); font-weight:600;">${row.gap.toFixed(2)} cm</td>
            <td>${row.length.toFixed(1)} cm</td>
        `;
        tbody.appendChild(tr);
    });
}

// Wykres 1: Histogram rozkładu
function renderHistogram(chartData, targetVal, lsl, usl) {
    const ctx = document.getElementById('histogramChart').getContext('2d');
    
    if (charts.histogram) {
        charts.histogram.destroy();
    }

    charts.histogram = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: 'Częstotliwość',
                data: chartData.values,
                backgroundColor: 'rgba(56, 189, 248, 0.4)',
                borderColor: '#38bdf8',
                borderWidth: 1.5,
                barPercentage: 1.0,
                categoryPercentage: 1.0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: true }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });
}

// Wykres 2: Run Chart (sekwencja produkcji)
function renderRunChart(chartData, targetVal, lsl, usl) {
    const ctx = document.getElementById('runChart').getContext('2d');
    
    if (charts.run) {
        charts.run.destroy();
    }

    // Przygotowanie linii Target, LSL, USL jako stałych tablic punktów
    const length = chartData.gaps.length;
    const targetLine = Array(length).fill(targetVal);
    const lslLine = Array(length).fill(lsl);
    const uslLine = Array(length).fill(usl);

    charts.run = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.indices,
            datasets: [
                {
                    label: 'Rozmiar luki (cm)',
                    data: chartData.gaps,
                    borderColor: 'rgba(56, 189, 248, 0.7)',
                    backgroundColor: 'transparent',
                    borderWidth: 1.5,
                    pointRadius: 1,
                    tension: 0.1
                },
                {
                    label: 'Target (Cel)',
                    data: targetLine,
                    borderColor: '#10b981',
                    borderWidth: 2,
                    pointRadius: 0,
                    borderDash: []
                },
                {
                    label: 'LSL (Dolny limit)',
                    data: lslLine,
                    borderColor: '#f43f5e',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    borderDash: [5, 5]
                },
                {
                    label: 'USL (Górny limit)',
                    data: uslLine,
                    borderColor: '#f43f5e',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#94a3b8' }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: { color: '#94a3b8', maxTicksLimit: 20 }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });
}

// Wykres 3: Korelacja (Wykres punktowy z linią trendu)
function renderCorrelationChart(chartData) {
    const ctx = document.getElementById('scatterChart').getContext('2d');
    
    if (charts.scatter) {
        charts.scatter.destroy();
    }

    const datasets = [{
        label: 'Dane kłód',
        data: chartData.points,
        backgroundColor: 'rgba(56, 189, 248, 0.6)',
        pointRadius: 3,
        type: 'scatter'
    }];

    // Jeśli mamy linię trendu, dodajemy ją do serii danych
    if (chartData.trendline && chartData.trendline.length > 1) {
        datasets.push({
            label: `Linia trendu OLS (R: ${chartData.coefficient.toFixed(3)})`,
            data: chartData.trendline,
            borderColor: '#f59e0b',
            borderWidth: 2,
            type: 'line',
            pointRadius: 0,
            fill: false
        });
    }

    charts.scatter = new Chart(ctx, {
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#94a3b8' }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    position: 'bottom',
                    title: { display: true, text: 'Długość kłody', color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    title: { display: true, text: 'Wielkość luki (cm)', color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });
}

// Generowanie porad Six Sigma
function generateLeanTips(cpk, stdDev, mean, target, kurtosis, skewness) {
    const tipText = document.getElementById('bb-tip-text');
    let advice = "";

    if (cpk >= 1.33) {
        advice = `🎉 <strong>Doskonały proces!</strong> Wskaźnik Cpk wynosi <strong>${cpk.toFixed(2)}</strong> (>= 1.33), co oznacza stabilny proces o znikomej liczbie defektów. Odchylenie standardowe (${stdDev.toFixed(2)}) jest pod kontrolą. Utrzymuj obecne nastawy maszyn.`;
    } else if (cpk >= 1.00) {
        advice = `⚠️ <strong>Proces marginalnie stabilny.</strong> Cpk = <strong>${cpk.toFixed(2)}</strong>. Proces mieści się w granicach tolerancji, ale margines bezpieczeństwa jest niewielki. `;
        if (Math.abs(mean - target) > 10) {
            advice += `Wartość średnia (${mean.toFixed(2)}) odbiega od celu (${target.toFixed(1)}). <strong>Zalecenie:</strong> Przesunięcie nastawy punktu zerowego maszyn w celu wycentrowania rozkładu.`;
        } else {
            advice += `Rozrzut (odchylenie standardowe = ${stdDev.toFixed(2)}) jest zbyt duży. <strong>Zalecenie:</strong> Kontrola luzów mechanicznych na podajnikach.`;
        }
    } else {
        advice = `🚨 <strong>Proces niestabilny (Cpk = ${cpk.toFixed(2)} < 1.00).</strong> Generujesz odpady produkcyjne (przekroczenia LSL/USL). `;
        
        if (kurtosis > 3) {
            advice += `Wysoka kurtoza (<strong>${kurtosis.toFixed(2)}</strong>) oznacza obecność "grubych ogonów", czyli wielu nagłych i niespodziewanych skoków luki (anomalii). **Skup się na usunięciu anomalii** przy użyciu checkboxa w panelu bocznym, aby sprawdzić, o ile wzrośnie Cpk po wyeliminowaniu sporadycznych zakłóceń. `;
        }
        
        if (Math.abs(mean - target) > 15) {
            advice += `Średnia luki (${mean.toFixed(2)}) bardzo mocno odbiega od wartości docelowej (${target.toFixed(1)}). Dokonaj kalibracji czujników pozycjonujących. `;
        }
    }
    
    tipText.innerHTML = advice;
}

// Loader i błędy
function showLoader(show) {
    const overlay = document.getElementById('loader-overlay');
    if (show) {
        overlay.classList.remove('hidden');
    } else {
        overlay.classList.add('hidden');
    }
}

function showError(msg) {
    const statusDiv = document.getElementById('file-status');
    statusDiv.classList.remove('hidden');
    statusDiv.classList.add('error');
    statusDiv.innerHTML = `<strong>Błąd:</strong> ${msg}`;
}

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import io
import numpy as np

# Sidekonfigurasjon
st.set_page_config(page_title="Stokklukeanalyse - Michal Kuszynski", layout="wide", page_icon="🌲")

# CSS for minimalistisk stil
st.markdown("""
<style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    h1, h2, h3 { font-family: 'Helvetica Neue', sans-serif; font-weight: 300; color: #2c3e50; }
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

st.title("📊 Stokklukeanalyse")
st.markdown("Dette verktøyet brukes til rask analyse av produksjonsdata (f.eks. `Snap.txt`) for prosessoptimalisering.")

# --- Funksjoner ---
def calculate_capability(data, lsl, usl):
    mean = data.mean()
    sigma = data.std()
    if sigma == 0: return 0, 0
    cp = (usl - lsl) / (6 * sigma)
    cpu = (usl - mean) / (3 * sigma)
    cpl = (mean - lsl) / (3 * sigma)
    cpk = min(cpu, cpl)
    return cp, cpk

# --- 1. Datainnlasting ---
st.sidebar.header("1. Datainnlasting")
uploaded_file = st.sidebar.file_uploader("Velg tekstfil (.txt, .csv)", type=['txt', 'csv'])

if uploaded_file is not None:
    try:
        encodings = ['utf-8', 'latin-1', 'cp1252']
        df = None
        for encoding in encodings:
            try:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, sep='\t', skipinitialspace=True, encoding=encoding)
                if len(df.columns) < 2:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, sep=',', encoding=encoding)
                break
            except: continue

        if df is None:
            st.error("Kunne ikke laste filen.")
            st.stop()

        df.columns = df.columns.str.strip()
        st.success(f"Fil lastet opp: {uploaded_file.name}")

        # --- 2. Konfigurasjon ---
        with st.sidebar.expander("⚙️ Konfigurasjon", expanded=True):
            all_columns = df.columns.tolist()
            default_gap = 'StoLucka' if 'StoLucka' in all_columns else all_columns[0]
            default_len = 'Längd' if 'Längd' in all_columns else (all_columns[1] if len(all_columns) > 1 else all_columns[0])
            col_gap = st.selectbox("Kolonne for lukestørrelse (StoLucka)", all_columns, index=all_columns.index(default_gap))
            col_len = st.selectbox("Kolonne for stokklengde (Längd)", all_columns, index=all_columns.index(default_len))
            
        # --- 3. Datarensing ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("🛠️ Datarensing og Filtrering")

        # Nytt: Checkbox for å aktivere/deaktivere filtrering
        enable_filter = st.sidebar.checkbox("Aktiver ekstra filtrering (f.eks. Klasse/InmDia)", value=True)
        
        filter_info = ""
        df_filtered = df
        
        if enable_filter:
            # Nytt: Valg for filtreringskolonne flyttet hit for oversiktlighet
            default_filter = 'InmDia' if 'InmDia' in all_columns else (all_columns[2] if len(all_columns) > 2 else all_columns[0])
            col_filter = st.sidebar.selectbox("Velg kolonne for filtrering", all_columns, index=all_columns.index(default_filter) if default_filter in all_columns else 0)
            
            # Filtrering basert på valgt kolonne
            if col_filter in df.columns:
                # Sjekk om dataene er numeriske for slider
                if pd.api.types.is_numeric_dtype(df[col_filter]):
                    min_val = int(df[col_filter].min())
                    max_val = int(df[col_filter].max())
                    
                    st.sidebar.markdown(f"**Filtrer på '{col_filter}':**")
                    filter_range = st.sidebar.slider(
                        "Velg område:",
                        min_value=min_val,
                        max_value=max_val,
                        value=(min_val, max_val)
                    )
                    
                    # Bruk filteret
                    df_filtered = df[
                        (df[col_filter] >= filter_range[0]) & 
                        (df[col_filter] <= filter_range[1])
                    ]
                    filter_info = f"Filter: {col_filter} {filter_range}."
                else:
                     st.sidebar.warning(f"Kolonnen '{col_filter}' er ikke numerisk og kan ikke filtreres med slider.")
                     df_filtered = df.copy() # Fallback
            
            df_clean = df_filtered[[col_gap, col_len, col_filter]].dropna()
        else:
            df_clean = df_filtered[[col_gap, col_len]].dropna()

        # Obliczanie obu granic anomalii (IQR)
        Q1 = df_clean[col_gap].quantile(0.25)
        Q3 = df_clean[col_gap].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        outliers_low = df_clean[df_clean[col_gap] < lower_bound]
        outliers_high = df_clean[df_clean[col_gap] > upper_bound]
        total_outliers_count = len(outliers_low) + len(outliers_high)

        exclude_outliers = st.sidebar.checkbox("Ekskluder ALLE anomalier", help="Fjerner både for lave og for høye verdier.")

        # --- 4. Prosessmål ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("🎯 Prosessmål (Lean)")
        target_val = st.sidebar.number_input("Ønsket luke (Target)", value=100.0)
        lsl = st.sidebar.number_input("Nedre grense (LSL)", value=50.0)
        usl = st.sidebar.number_input("Øvre grense (USL)", value=150.0)

        # Logika filtrowania
        if exclude_outliers:
            df_final = df_clean[(df_clean[col_gap] >= lower_bound) & (df_clean[col_gap] <= upper_bound)]
            st.warning(f"Analysen viser nå data UTEN anomalier ({total_outliers_count} rader fjernet). {filter_info}")
        else:
            df_final = df_clean
            if len(df) != len(df_final) and filter_info:
                 st.info(f"Viser filtrerte data. {filter_info}")

        if len(df_final) > 0:
            # --- STATISTIKK SEKSJON ---
            st.header("Statistikk og prosesskapasitet")
            
            stats = df_final[col_gap].describe()
            skewness = df_final[col_gap].skew()
            kurtosis = df_final[col_gap].kurt()
            correlation = df_final[col_len].corr(df_final[col_gap])
            cp, cpk = calculate_capability(df_final[col_gap], lsl, usl)

            r1c1, r1c2, r1c3, r1c4 = st.columns(4)
            r1c1.metric("Antall stokk", int(stats['count']))
            r1c2.metric("Gjennomsnitt", f"{stats['mean']:.2f}")
            r1c3.metric("Median luke", f"{stats['50%']:.2f}")
            r1c4.metric("Standardavvik", f"{stats['std']:.2f}")

            r2c1, r2c2, r2c3, r2c4 = st.columns(4)
            r2c1.metric("Skjevhet (Skewness)", f"{skewness:.2f}")
            r2c2.metric("Kurtose (Kurtosis)", f"{kurtosis:.2f}")
            r2c3.metric("Cp (Potensial)", f"{cp:.2f}")
            r2c4.metric("Cpk (Prosesskapasitet)", f"{cpk:.2f}")

            # --- ANALYSE AV ANOMALIER ---
            # --- ANALYSE AV ANOMALIER ---
            outliers_df = pd.concat([outliers_low, outliers_high])
            num_outliers = len(outliers_df)
            percent_outliers = (num_outliers / len(df_clean)) * 100

            st.header("🚨 Analyse av anomalier (Outliers)")
            st.markdown(f"""
            Denne analysen bruker **IQR-metoden** (Interquartile Range) for å identifisere klogger som skaper 
            unaturlig store luker i produksjonen.
            """)

            a1, a2, a3 = st.columns(3)
            a1.metric("For høye (Sløsing)", len(outliers_high), delta=f"> {upper_bound:.1f} cm", delta_color="inverse")
            a2.metric("For lave (Risiko)", len(outliers_low), delta=f"< {lower_bound:.1f} cm", delta_color="inverse")
            a3.metric("Total andel avvik", f"{percent_outliers:.2f}%")

            if num_outliers > 0:
                with st.expander("Se detaljert liste over anomalier"):
                    col_tab1, col_tab2 = st.columns(2)
                    with col_tab1:
                        st.write(f"**Høye anomalier (> {upper_bound:.1f} cm):**")
                        st.dataframe(outliers_high.sort_values(by=col_gap, ascending=False))
                    with col_tab2:
                        st.write(f"**Lave anomalier (< {lower_bound:.1f} cm):**")
                        st.dataframe(outliers_low.sort_values(by=col_gap, ascending=True))
                    
                    st.info(f"""
                    **Tips for Black Belt:** Disse kloggene er hovedårsaken til den høye kurtosen ({kurtosis:.2f}) 
                    og den lave Cpk-verdien. Ved å eliminere årsakene til disse få kloggene, 
                    vil prosessstabiliteten øke betydelig.
                    """)

            # --- VISUALISERINGER ---
            st.header("Visualiseringer")
            tab1, tab2, tab3 = st.tabs(["Histogram", "Run Chart", "Interaktiv Korrelasjon"])

            with tab1:
                fig1, ax1 = plt.subplots(figsize=(10, 5))
                sns.histplot(df_final[col_gap], kde=True, color='royalblue', ax=ax1)
                ax1.axvline(lsl, color='red', linestyle='--', label=f'LSL ({lsl})')
                ax1.axvline(usl, color='red', linestyle='--', label=f'USL ({usl})')
                ax1.axvline(target_val, color='green', linestyle='-', linewidth=2, label=f'Target ({target_val})')
                ax1.legend()
                st.pyplot(fig1)

            with tab2:
                fig2 = px.line(df_final, y=col_gap, title="Produksjonssekvens")
                fig2.add_hline(y=target_val, line_dash="solid", line_color="green", annotation_text="Target")
                st.plotly_chart(fig2, use_container_width=True)

            with tab3:
                fig3 = px.scatter(df_final, x=col_len, y=col_gap, trendline="ols",
                                  hover_data=[df_final.index], 
                                  title=f"Korrelasjon (Pearson: {correlation:.4f})",
                                  labels={col_len: "Stokklengde", col_gap: "Luka"})
                st.plotly_chart(fig3, use_container_width=True)

    except Exception as e:
        st.error(f"En feil oppstod: {e}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Utviklet av Michal Kuszynski**  \n[www.leansixsigma.no](http://www.leansixsigma.no)")
else:
    st.info("👈 Vennligst last opp Snap.txt i sidefeltet.")
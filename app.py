import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import io

# Konfigurasjon av siden
st.set_page_config(page_title="StokkLukka analyse - Michal Kuszynski", layout="wide", page_icon="🌲")

st.title("📊 StokkLukka analyseverktøy")
st.markdown("""
<style>
    /* Minimalistyczny styl */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1 {
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 300;
        color: #2c3e50;
    }
    h2, h3 {
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 300;
        color: #34495e;
    }
    /* Ukrycie stopki Streamlit */
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}

</style>
Dette verktøyet brukes til rask analyse av data fra tekstfiler (f.eks. `Snap.txt`).
Last opp filen, velg kolonner og se statistikk og grafer.
""", unsafe_allow_html=True)


# 1. Last opp data
st.sidebar.header("1. Last opp data")
uploaded_file = st.sidebar.file_uploader("Velg tekstfil (.txt, .csv)", type=['txt', 'csv'])


if uploaded_file is not None:
    try:
        # Próba wczytania danych z obsługą różnych kodowań (Leaving comments in code as is or translating? logic remains)
        encodings = ['utf-8', 'latin-1', 'cp1252']
        df = None
        
        for encoding in encodings:
            try:
                uploaded_file.seek(0)
                # Prøver tabulator først
                df = pd.read_csv(uploaded_file, sep='\t', skipinitialspace=True, encoding=encoding)
                if len(df.columns) < 2: # Hvis få kolonner, prøv komma
                     uploaded_file.seek(0)
                     df = pd.read_csv(uploaded_file, sep=',', encoding=encoding)
                break 
            except UnicodeDecodeError:
                continue 
            except Exception:
                uploaded_file.seek(0)
                try:
                     df = pd.read_csv(uploaded_file, sep=',', encoding=encoding)
                     break
                except:
                     continue

        if df is None:
             st.error(f"Kunne ikke laste filen. Sjekk om det er en gyldig tekst/CSV-fil (koding: {', '.join(encodings)}).")
             st.stop()
        
        # Rensing av kolonnenavn
        df.columns = df.columns.str.strip()
        
        st.success(f"Fil lastet opp: {uploaded_file.name} ({len(df)} rader)")
        
        with st.expander("Forhåndsvisning av rådata"):
            st.dataframe(df.head())

        # 2. Valg av kolonner
        with st.sidebar.expander("⚙️ Konfigurasjon", expanded=True):
            all_columns = df.columns.tolist()
            
            # Forsøk på automatisk valg
            default_gap = 'StoLucka' if 'StoLucka' in all_columns else all_columns[0]
            default_len = 'Lengde' if 'Lengde' in all_columns else (all_columns[1] if len(all_columns) > 1 else all_columns[0])
            
            col_gap = st.selectbox("Velg kolonne for Lukestørrelse (f.eks. StoLucka)", all_columns, index=all_columns.index(default_gap))
            col_len = st.selectbox("Velg kolonne for Stokklengde (f.eks. Lengde)", all_columns, index=all_columns.index(default_len))
        
        
        # Filtrering
        st.sidebar.markdown("---")
        st.sidebar.subheader("Filtrering")

        # 1. Numerisk filter (Diameter/InmDia) for hele tall
        use_num_filter = st.sidebar.checkbox("Filtrer etter Diameter/Mål")
        if use_num_filter:
            default_num = 'InmDia' if 'InmDia' in all_columns else all_columns[0]
            col_num = st.sidebar.selectbox("Velg kolonne (f.eks. InmDia)", all_columns, index=all_columns.index(default_num) if default_num in all_columns else 0)
            
            if pd.api.types.is_numeric_dtype(df[col_num]):
                min_val = int(df[col_num].min())
                max_val = int(df[col_num].max())
                
                # Zabezpieczenie przed błędem gdy min=max
                if min_val == max_val:
                    st.sidebar.info(f" Kun én verdi i dataene: {min_val}")
                else:
                    range_vals = st.sidebar.slider(f"Velg område for {col_num}", min_val, max_val, (min_val, max_val), step=1)
                    df = df[(df[col_num] >= range_vals[0]) & (df[col_num] <= range_vals[1])]
            else:
                st.sidebar.error(f"Kolonnen {col_num} er ikke numerisk!")

        st.sidebar.info(f"Viser {len(df)} rader (etter filter).")
        
        # Filtrering av kolonner for analyse
        df_clean = df[[col_gap, col_len]].dropna()
        
        if len(df_clean) == 0:
            st.error("Ingen data etter fjerning av tomme verdier i valgte kolonner.")
        else:
            # 3. Statistikk
            st.header("Statistikk og analyse")
            
            stats = df_clean[col_gap].describe()
            correlation = df_clean[col_len].corr(df_clean[col_gap])
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Antall prøver", int(stats['count']))
            with c2:
                st.metric("Gjennomsnittlig gape", f"{stats['mean']:.2f}")
            with c3:
                st.metric("Standardavvik", f"{stats['std']:.2f}")

            st.write(f"**Pearson-korrelasjon ({col_len} vs {col_gap}):** `{correlation:.4f}`")
            
            with st.expander("Detaljert beskrivende statistikk"):
                st.table(stats)

            # Stil - Minimalistisk
            sns.set_theme(style="ticks", rc={"axes.spines.right": False, "axes.spines.top": False})

            # 4. Visualiseringer
            st.header("Visualiseringer")

            tab1, tab2, tab3 = st.tabs(["Histogram (Fordeling)", "Tidslinje (Run Chart)", "Korrelasjon (Scatter)"])

            with tab1:
                st.subheader("Fordeling av lukestørrelse (Stabilitet)")
                fig1, ax1 = plt.subplots(figsize=(10, 6))
                sns.histplot(df_clean[col_gap], kde=True, color='royalblue', bins=30, ax=ax1)
                ax1.set_xlabel(f'{col_gap} (Enhet)', fontsize=12)
                ax1.set_ylabel('Antall observasjoner', fontsize=12)
                ax1.axvline(stats['mean'], color='red', linestyle='--', label=f"Gjennomsnitt: {stats['mean']:.2f}")
                ax1.legend()
                st.pyplot(fig1)

            with tab2:
                st.subheader("Lukestørrelse over tid (Trender)")
                fig2, ax2 = plt.subplots(figsize=(12, 6))
                ax2.plot(df_clean.index, df_clean[col_gap], marker='o', markersize=3, 
                         linestyle='-', alpha=0.6, color='forestgreen')
                ax2.axhline(stats['mean'], color='red', linestyle='--', linewidth=2, label='Gjennomsnitt')
                ax2.axhline(stats['mean'] + stats['std'], color='orange', linestyle=':', label='+1 Sigma')
                ax2.axhline(stats['mean'] - stats['std'], color='orange', linestyle=':', label='-1 Sigma')
                ax2.set_xlabel('Rekkefølge (Logg nr.)', fontsize=12)
                ax2.set_ylabel(f'{col_gap}', fontsize=12)
                ax2.legend(loc='upper right')
                st.pyplot(fig2)

            with tab3:
                st.subheader("Korrelasjon: Stokklengde vs. Lukestørrelse")
                fig3, ax3 = plt.subplots(figsize=(10, 6))
                sns.regplot(data=df_clean, x=col_len, y=col_gap, ax=ax3,
                            scatter_kws={'alpha':0.4, 'color':'teal'}, 
                            line_kws={'color':'red', 'label':'Trendlinje'})
                ax3.set_title(f'Pearson korrelasjon: {correlation:.2f}', fontsize=12)
                ax3.set_xlabel(f'{col_len} (Stokklengde)', fontsize=12)
                ax3.set_ylabel(f'{col_gap} (Lukestørrelse)', fontsize=12)
                ax3.legend()
                st.pyplot(fig3)

    except Exception as e:
        st.error(f"En feil oppstod under behandling av filen: {e}")

    # Info om forfatter (Footer)
    st.sidebar.markdown("---")
    with st.sidebar.expander("ℹ️ Kontakt"):
        st.markdown("""
        **Utviklet av:** Michal Kuszynski  
        Verktøy for Six Sigma analyse av tømmerdata.
        
        © 2026 www.leansixsigma.no
        """)
else:
    st.info("👈 Last opp datafilen i sidefeltet for å starte analysen.")

import streamlit as st
import pandas as pd
import io
import xlsxwriter

# --- Konfigurasi Halaman ---
st.set_page_config(page_title="Sistem RAB Pro", layout="wide")

# --- 1. Inisialisasi Data (Dummy Data) ---
def initialize_data():
    if 'df_prices' not in st.session_state:
        # Data Harga Dasar (Resources)
        data_prices = {
            'Kode': ['M.01', 'M.02', 'M.03', 'L.01', 'L.02'],
            'Komponen': ['Semen Portland', 'Pasir Beton', 'Batu Kali', 'Pekerja', 'Tukang Batu'],
            'Satuan': ['kg', 'kg', 'm3', 'OH', 'OH'],
            'Harga_Dasar': [1300, 300, 286500, 100000, 145000],
            'Kategori': ['Material', 'Material', 'Material', 'Upah', 'Upah']
        }
        st.session_state['df_prices'] = pd.DataFrame(data_prices)

    if 'df_analysis' not in st.session_state:
        # Data Analisa (AHSP SNI)
        data_analysis = {
            'Kode_Analisa': ['A.2.2.1', 'A.2.2.1', 'A.2.2.1', 'A.2.2.1', 'A.2.2.1', 
                             'A.4.1.1', 'A.4.1.1', 'A.4.1.1', 'A.4.1.1'],
            'Uraian_Pekerjaan': ['Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4',
                                 'Beton Mutu fc 25 Mpa', 'Beton Mutu fc 25 Mpa', 'Beton Mutu fc 25 Mpa', 'Beton Mutu fc 25 Mpa'],
            'Komponen': ['Batu Kali', 'Semen Portland', 'Pasir Beton', 'Pekerja', 'Tukang Batu',
                         'Semen Portland', 'Pasir Beton', 'Split (Asumsi)', 'Pekerja'],
            'Koefisien': [1.2, 163.0, 0.52, 1.5, 0.75,
                          350.0, 700.0, 1050.0, 2.0]
        }
        st.session_state['df_analysis'] = pd.DataFrame(data_analysis)

    if 'df_rab' not in st.session_state:
        # Data RAB (Volume Project)
        data_rab = {
            'No': [1, 2],
            'Uraian_Pekerjaan': ['Pondasi Batu Kali 1:4', 'Beton Mutu fc 25 Mpa'],
            'Kode_Analisa_Ref': ['A.2.2.1', 'A.4.1.1'],
            'Satuan_Pek': ['m3', 'm3'],
            'Volume': [50.0, 25.0],
            'Harga_Satuan_Jadi': [0.0, 0.0],
            'Total_Harga': [0.0, 0.0]
        }
        st.session_state['df_rab'] = pd.DataFrame(data_rab)
        
    # Trigger kalkulasi awal agar angka tidak 0
    calculate_system()

# --- 2. Mesin Logika Utama ---
def calculate_system():
    df_p = st.session_state['df_prices'].copy()
    df_a = st.session_state['df_analysis'].copy()
    df_r = st.session_state['df_rab'].copy()

    # Normalisasi Key untuk matching
    df_p['Key'] = df_p['Komponen'].str.strip().str.lower()
    df_a['Key'] = df_a['Komponen'].str.strip().str.lower()

    # 1. Hitung Harga Satuan per Analisa
    # FIX: Menambahkan kolom 'Satuan' agar ikut terbawa saat merge
    merged_analysis = pd.merge(df_a, df_p[['Key', 'Harga_Dasar', 'Satuan']], on='Key', how='left')
    
    merged_analysis['Harga_Dasar'] = merged_analysis['Harga_Dasar'].fillna(0)
    # Isi Satuan yang kosong (misal item baru) dengan '-' agar tidak error
    merged_analysis['Satuan'] = merged_analysis['Satuan'].fillna('-')
    
    merged_analysis['Subtotal'] = merged_analysis['Koefisien'] * merged_analysis['Harga_Dasar']
    
    # Simpan detail kalkulasi analisa ke session untuk ditampilkan di Tab AHSP
    st.session_state['df_analysis_detailed'] = merged_analysis 

    # Agregat Harga Satuan Jadi
    unit_prices = merged_analysis.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices.rename(columns={'Subtotal': 'Harga_Kalkulasi'}, inplace=True)

    # 2. Update RAB
    df_r_temp = pd.merge(df_r, unit_prices, left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
    df_r['Harga_Satuan_Jadi'] = df_r_temp['Harga_Kalkulasi'].fillna(0)
    df_r['Total_Harga'] = df_r['Volume'] * df_r['Harga_Satuan_Jadi']
    st.session_state['df_rab'] = df_r

    # 3. Hitung Rekap Material (Volume Proyek x Koefisien)
    # Merge RAB (Volume) dengan Analisa (Koefisien)
    material_breakdown = pd.merge(
        df_r[['Kode_Analisa_Ref', 'Volume']], 
        merged_analysis[['Kode_Analisa', 'Komponen', 'Satuan', 'Koefisien', 'Harga_Dasar']], 
        left_on='Kode_Analisa_Ref', 
        right_on='Kode_Analisa', 
        how='left'
    )
    
    # Rumus: Volume Proyek * Koefisien
    material_breakdown['Total_Kebutuhan_Material'] = material_breakdown['Volume'] * material_breakdown['Koefisien']
    material_breakdown['Total_Biaya_Material'] = material_breakdown['Total_Kebutuhan_Material'] * material_breakdown['Harga_Dasar']
    
    # Group by Material
    rekap_final = material_breakdown.groupby(['Komponen', 'Satuan']).agg({
        'Total_Kebutuhan_Material': 'sum',
        'Total_Biaya_Material': 'sum'
    }).reset_index()
    
    st.session_state['df_material_rekap'] = rekap_final


# --- 3. Fungsi Helper Excel ---
def load_excel_prices(uploaded_file):
    try:
        df_new = pd.read_excel(uploaded_file)
        # Validasi kolom minimal
        required = ['Komponen', 'Harga_Dasar']
        if not set(required).issubset(df_new.columns):
            st.error(f"Format Excel salah! Wajib ada kolom: {required}")
            return
        
        # Update harga
        st.session_state['df_prices'] = df_new
        calculate_system()
        st.success("Harga berhasil diupdate!")
    except Exception as e:
        st.error(f"Gagal membaca file: {e}")

def load_excel_rab_volume(uploaded_file):
    try:
        df_new = pd.read_excel(uploaded_file)
        required = ['Uraian_Pekerjaan', 'Kode_Analisa_Ref', 'Volume']
        if not set(required).issubset(df_new.columns):
            st.error(f"Format Excel salah! Wajib ada kolom: {required}")
            return
        
        # Kita ambil kolom penting saja dan reset kolom hitungan
        df_clean = df_new[required].copy()
        df_clean['No'] = range(1, len(df_clean) + 1)
        df_clean['Satuan_Pek'] = 'ls/m3/m2' 
        df_clean['Harga_Satuan_Jadi'] = 0
        df_clean['Total_Harga'] = 0
        
        st.session_state['df_rab'] = df_clean
        calculate_system()
        st.success("Volume RAB berhasil diimport!")
    except Exception as e:
        st.error(f"Gagal membaca file: {e}")

# --- 4. Main UI ---
def main():
    initialize_data()
    
    st.title("🏗️ Sistem Integrated RAB & Material Control")
    
    # Urutan Menu Baru
    tabs = st.tabs([
        "📊 1. REKAPITULASI", 
        "📝 2. RAB PROYEK", 
        "🔍 3. AHSP SNI", 
        "💰 4. HARGA SATUAN", 
        "🧱 5. REKAP MATERIAL"
    ])

    # === TAB 1: REKAPITULASI ===
    with tabs[0]:
        st.header("Rekapitulasi Biaya Proyek")
        grand_total = st.session_state['df_rab']['Total_Harga'].sum()
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Rencana Anggaran Biaya", f"Rp {grand_total:,.0f}")
        
        with col2:
            st.info("Ringkasan ini otomatis terhitung dari Tab RAB.")
            
        if 'df_material_rekap' in st.session_state:
             st.write("---")
             st.subheader("Porsi Biaya Terbesar (Top 5 Material)")
             # Chart sederhana
             top_mat = st.session_state['df_material_rekap'].sort_values('Total_Biaya_Material', ascending=False).head(5)
             st.bar_chart(top_mat, x="Komponen", y="Total_Biaya_Material")

    # === TAB 2: RAB (Input Volume & Excel) ===
    with tabs[1]:
        st.header("Rencana Anggaran Biaya")
        
        # Fitur Upload Excel Volume
        with st.expander("📂 Import Volume dari Excel"):
            st.markdown("Pastikan Excel memiliki kolom: `Uraian_Pekerjaan`, `Kode_Analisa_Ref`, `Volume`")
            uploaded_rab = st.file_uploader("Upload File Volume", type=['xlsx'], key="upload_rab")
            if uploaded_rab:
                load_excel_rab_volume(uploaded_rab)

        # Editor RAB
        st.caption("Silakan edit Volume di bawah ini:")
        edited_rab = st.data_editor(
            st.session_state['df_rab'],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "No": st.column_config.NumberColumn(disabled=True),
                "Uraian_Pekerjaan": st.column_config.TextColumn(disabled=True),
                "Kode_Analisa_Ref": st.column_config.TextColumn(disabled=True),
                "Harga_Satuan_Jadi": st.column_config.NumberColumn("Harga Satuan", format="Rp %d", disabled=True),
                "Total_Harga": st.column_config.NumberColumn("Total", format="Rp %d", disabled=True),
                "Volume": st.column_config.NumberColumn("Volume (Input)", help="Isi volume disini")
            }
        )
        
        if not edited_rab.equals(st.session_state['df_rab']):
            st.session_state['df_rab'] = edited_rab
            calculate_system()
            st.rerun()

    # === TAB 3: AHSP SNI (Read Only Detail) ===
    with tabs[2]:
        st.header("Analisa Harga Satuan Pekerjaan (AHSP)")
        st.markdown("Detail koefisien dan harga pembentuk (Read-Only).")
        
        # Tampilkan DataFrame detail yang sudah ada harga & total per barisnya
        view_ahsp = st.session_state['df_analysis_detailed'][
            ['Kode_Analisa', 'Uraian_Pekerjaan', 'Komponen', 'Koefisien', 'Satuan', 'Harga_Dasar', 'Subtotal']
        ]
        
        st.dataframe(
            view_ahsp,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Harga_Dasar": st.column_config.NumberColumn(format="Rp %d"),
                "Subtotal": st.column_config.NumberColumn(format="Rp %d"),
            }
        )

    # === TAB 4: HARGA SATUAN (Input Harga & Excel) ===
    with tabs[3]:
        st.header("Master Harga Satuan Dasar")
        
        # Fitur Upload Excel Harga
        with st.expander("📂 Import Harga dari Excel"):
            st.markdown("Pastikan Excel memiliki kolom: `Komponen`, `Harga_Dasar`, `Satuan`")
            uploaded_price = st.file_uploader("Upload File Harga", type=['xlsx'], key="upload_price")
            if uploaded_price:
                load_excel_prices(uploaded_price)

        # Editor Harga
        edited_prices = st.data_editor(
            st.session_state['df_prices'],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Harga_Dasar": st.column_config.NumberColumn("Harga Dasar (Input)", format="Rp %d")
            }
        )
        
        if not edited_prices.equals(st.session_state['df_prices']):
            st.session_state['df_prices'] = edited_prices
            calculate_system()
            st.rerun()

    # === TAB 5: REKAP MATERIAL (Breakdown) ===
    with tabs[4]:
        st.header("Rekapitulasi Kebutuhan Material")
        st.markdown("""
        Tabel ini menghitung total logistik yang harus dibeli berdasarkan:  
        **Volume RAB x Koefisien AHSP**.
        """)
        
        if 'df_material_rekap' in st.session_state:
            st.dataframe(
                st.session_state['df_material_rekap'],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Total_Kebutuhan_Material": st.column_config.NumberColumn("Total Volume", format="%.2f"),
                    "Total_Biaya_Material": st.column_config.NumberColumn("Total Biaya", format="Rp %d")
                }
            )
            
            total_mat_cost = st.session_state['df_material_rekap']['Total_Biaya_Material'].sum()
            st.metric("Total Belanja Material & Upah", f"Rp {total_mat_cost:,.0f}")
        else:
            st.warning("Data belum tersedia. Silakan isi RAB terlebih dahulu.")

if __name__ == "__main__":
    main()

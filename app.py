import streamlit as st
import pandas as pd
import io
import xlsxwriter

# --- Kofigurasi Halaman ---
st.set_page_config(page_title="Sistem RAB Otomatis AHSP 2025", layout="wide")

# --- 1. Inisialisasi Data (Dummy Data sesuai Prompt) ---
def initialize_data():
    if 'df_prices' not in st.session_state:
        # Layer 1: Sumber Daya Dasar
        data_prices = {
            'Kode': ['M.01', 'M.02', 'M.03', 'L.01', 'L.02'],
            'Komponen': ['Semen Portland', 'Pasir Beton', 'Batu Kali', 'Pekerja', 'Tukang Batu'],
            'Satuan': ['kg', 'kg', 'm3', 'OH', 'OH'],
            'Harga_Dasar': [1300, 300, 286500, 100000, 145000],
            'Kategori': ['Material', 'Material', 'Material', 'Upah', 'Upah']
        }
        st.session_state['df_prices'] = pd.DataFrame(data_prices)

    if 'df_analysis' not in st.session_state:
        # Layer 2: Analisa (Resep) - Perhatikan nama komponen harus match dengan Layer 1
        data_analysis = {
            'Kode_Analisa': ['A.2.2.1', 'A.2.2.1', 'A.2.2.1', 'A.2.2.1', 'A.2.2.1', 
                             'A.4.1.1', 'A.4.1.1', 'A.4.1.1', 'A.4.1.1'],
            'Uraian_Pekerjaan': ['Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4',
                                 'Beton Mutu fc 25 Mpa', 'Beton Mutu fc 25 Mpa', 'Beton Mutu fc 25 Mpa', 'Beton Mutu fc 25 Mpa'],
            'Komponen': ['Batu Kali', 'Semen Portland', 'Pasir Beton', 'Pekerja', 'Tukang Batu',
                         'Semen Portland', 'Pasir Beton', 'Split (Asumsi)', 'Pekerja'], # Split tidak ada di master, akan jadi NaN/0 (perlu handling)
            'Koefisien': [1.2, 163.0, 0.52, 1.5, 0.75,
                          350.0, 700.0, 1050.0, 2.0]
        }
        st.session_state['df_analysis'] = pd.DataFrame(data_analysis)

    if 'df_rab' not in st.session_state:
        # Layer 3: RAB (Volume Project)
        data_rab = {
            'No': [1, 2],
            'Uraian_Pekerjaan': ['Pondasi Batu Kali 1:4', 'Beton Mutu fc 25 Mpa'], # Harus sama dengan Kode/Uraian di Analisa
            'Kode_Analisa_Ref': ['A.2.2.1', 'A.4.1.1'], # Link key
            'Satuan_Pek': ['m3', 'm3'],
            'Volume': [50.0, 25.0],
            'Harga_Satuan_Jadi': [0.0, 0.0], # Akan dihitung otomatis
            'Total_Harga': [0.0, 0.0]       # Akan dihitung otomatis
        }
        st.session_state['df_rab'] = pd.DataFrame(data_rab)

# --- 2. Mesin Logika (The Calculation Engine) ---
def calculate_system():
    """
    Fungsi ini melakukan 'Re-Linking' seluruh data dari Harga -> Analisa -> RAB
    Setiap kali ada perubahan input, fungsi ini dipanggil.
    """
    # Ambil data dari state
    df_p = st.session_state['df_prices'].copy()
    df_a = st.session_state['df_analysis'].copy()
    df_r = st.session_state['df_rab'].copy()

    # --- LANGKAH 1: Normalisasi String (Fuzzy Matching Sederhana) ---
    # Memastikan 'Semen Portland ' sama dengan 'semen portland'
    df_p['Key'] = df_p['Komponen'].str.strip().str.lower()
    df_a['Key'] = df_a['Komponen'].str.strip().str.lower()

    # --- LANGKAH 2: Hitung Harga Satuan Analisa (Layer 1 -> Layer 2) ---
    # Merge Master Harga ke Tabel Analisa
    merged_analysis = pd.merge(df_a, df_p[['Key', 'Harga_Dasar']], on='Key', how='left')
    
    # Handle NaN (Material yang ada di analisa tapi lupa dimasukkan harganya di Master)
    merged_analysis['Harga_Dasar'] = merged_analysis['Harga_Dasar'].fillna(0)
    
    # Hitung Subtotal per baris komponen
    merged_analysis['Subtotal'] = merged_analysis['Koefisien'] * merged_analysis['Harga_Dasar']
    
    # Group by Kode Analisa untuk dapat Harga Jadi per 1 m3/m2
    # Hasilnya adalah Series: {'A.2.2.1': Rp X, 'A.4.1.1': Rp Y}
    unit_prices = merged_analysis.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices.rename(columns={'Subtotal': 'Harga_Kalkulasi'}, inplace=True)

    # --- LANGKAH 3: Update RAB (Layer 2 -> Layer 3) ---
    # Merge Harga Jadi ke Tabel RAB berdasarkan Kode Referensi
    # Kita gunakan temporary column untuk merge agar urutan baris RAB tidak berantakan
    df_r_temp = pd.merge(df_r, unit_prices, left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
    
    # Update kolom Harga_Satuan_Jadi & Total
    df_r['Harga_Satuan_Jadi'] = df_r_temp['Harga_Kalkulasi'].fillna(0)
    df_r['Total_Harga'] = df_r['Volume'] * df_r['Harga_Satuan_Jadi']

    # Simpan kembali ke state
    st.session_state['df_rab'] = df_r
    
    # Debug info (Opsional, bisa dihapus)
    # st.toast("Kalkulasi Ulang Selesai!", icon="✅")

# --- 3. Fungsi Utilitas Excel ---
def to_excel(df_list, sheet_names):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    for df, sheet in zip(df_list, sheet_names):
        df.to_excel(writer, index=False, sheet_name=sheet)
        # Auto-adjust column width
        worksheet = writer.sheets[sheet]
        for idx, col in enumerate(df):
            series = df[col]
            max_len = max((series.astype(str).map(len).max(), len(str(series.name)))) + 1
            worksheet.set_column(idx, idx, max_len)
    writer.close()
    processed_data = output.getvalue()
    return processed_data

# --- 4. Main UI Application ---
def main():
    initialize_data()
    
    st.title("🏗️ Sistem RAB Otomatis - AHSP 2025")
    st.markdown("""
    *Aplikasi Estimasi Biaya Konstruksi Berbasis Python dengan Integrasi Data Relasional.*
    """)

    # Tab Navigasi
    tab1, tab2, tab3 = st.tabs(["💰 1. Harga Dasar (Resources)", "⚙️ 2. Analisa (AHSP)", "📝 3. RAB Proyek"])

    # --- TAB 1: HARGA DASAR (Editable) ---
    with tab1:
        st.info("Input harga bahan dan upah terbaru di sini. Perubahan akan otomatis mengupdate RAB.")
        
        # Editor Harga
        edited_prices = st.data_editor(
            st.session_state['df_prices'],
            num_rows="dynamic",
            key="editor_prices",
            use_container_width=True,
            column_config={
                "Harga_Dasar": st.column_config.NumberColumn(
                    "Harga Dasar (Rp)", format="Rp %d"
                )
            }
        )
        
        # Cek jika ada perubahan, simpan ke state & trigger kalkulasi
        if not edited_prices.equals(st.session_state['df_prices']):
            st.session_state['df_prices'] = edited_prices
            calculate_system() # TRIGGER LINKING
            st.rerun()

    # --- TAB 2: ANALISA (Read-Only Logic) ---
    with tab2:
        st.warning("⚠️ Tab ini berisi Resep/Koefisien SNI. Bersifat Read-Only untuk user umum.")
        
        st.dataframe(
            st.session_state['df_analysis'],
            use_container_width=True,
            hide_index=True
        )
        
        with st.expander("Lihat Detail Kalkulasi Harga Satuan"):
            # Tampilkan hasil join untuk transparansi
            df_p = st.session_state['df_prices']
            df_a = st.session_state['df_analysis']
            # Simple merge display
            view = pd.merge(
                df_a, 
                df_p[['Komponen', 'Harga_Dasar']], 
                on='Komponen', 
                how='left'
            )
            view['Total'] = view['Koefisien'] * view['Harga_Dasar']
            st.dataframe(view)

    # --- TAB 3: RAB PROYEK (Volume Input) ---
    with tab3:
        st.success("Masukkan Volume pekerjaan. Harga Satuan terisi otomatis dari Tab 1 & 2.")
        
        # Editor RAB
        edited_rab = st.data_editor(
            st.session_state['df_rab'],
            num_rows="dynamic",
            key="editor_rab",
            use_container_width=True,
            column_config={
                "No": st.column_config.NumberColumn(disabled=True),
                "Uraian_Pekerjaan": st.column_config.TextColumn(disabled=True), # Idealnya dropdown
                "Kode_Analisa_Ref": st.column_config.TextColumn(disabled=True),
                "Harga_Satuan_Jadi": st.column_config.NumberColumn(
                    "Harga Satuan (Rp)", format="Rp %d", disabled=True
                ),
                "Total_Harga": st.column_config.NumberColumn(
                    "Total Harga (Rp)", format="Rp %d", disabled=True
                ),
                "Volume": st.column_config.NumberColumn(
                    "Volume", help="Input volume disini"
                )
            }
        )

        # Cek perubahan volume
        if not edited_rab.equals(st.session_state['df_rab']):
            st.session_state['df_rab'] = edited_rab
            calculate_system()
            st.rerun()

        # Grand Total
        grand_total = st.session_state['df_rab']['Total_Harga'].sum()
        st.metric(label="Total Estimasi Biaya Proyek", value=f"Rp {grand_total:,.0f}")

        # Download Button
        excel_file = to_excel(
            [st.session_state['df_prices'], st.session_state['df_analysis'], st.session_state['df_rab']], 
            ['Harga_Dasar', 'Analisa', 'RAB']
        )
        st.download_button(
            label="📥 Unduh Laporan Excel",
            data=excel_file,
            file_name='RAB_Otomatis_AHSP2025.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

if __name__ == "__main__":
    main()

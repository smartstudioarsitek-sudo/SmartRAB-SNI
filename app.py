import streamlit as st
import pandas as pd
import io
import re
import altair as alt
import xlsxwriter

# ==========================================
# 1. KONFIGURASI DAN UTILITAS SISTEM
# ==========================================
st.set_page_config(page_title="SmartRAB-SNI 2025", layout="wide", page_icon="🏗️")

def clean_currency_str(val):
    """
    Membersihkan format mata uang Indonesia (Rp 1.000.000,00) menjadi float.
    Menghapus 'Rp', titik ribuan, dan menangani koma desimal.
    """
    if pd.isna(val) or val == '':
        return 0.0
    # Hapus Rp, spasi, dan titik pemisah ribuan
    s = str(val).replace('Rp', '').replace('.', '').replace(' ', '')
    # Ganti koma desimal dengan titik
    s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0

def clean_coefficient(val):
    """
    Membersihkan format koefisien. Menangani koma sebagai desimal.
    """
    if pd.isna(val) or val == '':
        return 0.0
    s = str(val).replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0

def normalize_text(text):
    """
    Normalisasi teks untuk pencocokan fuzzy sederhana.
    Lowercase, strip whitespace, hapus tanda baca minor.
    """
    if not isinstance(text, str):
        return ""
    return text.lower().strip().replace('"', '').replace("'", "")

# ==========================================
# 2. MESIN ETL (AHSP DATA MANAGER)
# ==========================================
class AHSPDataManager:
    """
    Kelas pengendali data untuk memproses file CSV SNI AHSP.
    Bertanggung jawab atas parsing, cleaning, dan strukturisasi data.
    """
    def __init__(self):
        # Inisialisasi Session State jika belum ada
        if 'db_prices' not in st.session_state:
            st.session_state.db_prices = pd.DataFrame()
        if 'db_analysis' not in st.session_state:
            # Dictionary untuk menyimpan struktur pohon analisis
            # Key: Kode Analisa, Value: Dict detail
            st.session_state.db_analysis = {} 

    def load_basic_prices(self, file_obj):
        """
        Memproses file 'Upah Bahan.csv'.
        File ini adalah sumber kebenaran (source of truth) untuk harga dasar.
        """
        try:
            # File SNI biasanya memiliki header metadata di baris-baris awal
            # Kita skip 6 baris pertama berdasarkan struktur 
            df = pd.read_csv(file_obj, header=None, skiprows=6)
            
            # Mapping kolom berdasarkan standar SNI
            # Col 1: Kode, Col 2: Uraian, Col 3: Satuan, Col 4: Harga
            df_clean = df.iloc[:, ].copy()
            df_clean.columns =
            
            # Data Cleaning
            df_clean = df_clean.dropna(subset=['Uraian'])
            df_clean['Harga'] = df_clean['Harga'].apply(clean_currency_str)
            df_clean['Uraian_Norm'] = df_clean['Uraian'].apply(normalize_text)
            
            # Kategorisasi Otomatis berdasarkan Kode
            def get_category(code):
                c = str(code).upper()
                if c.startswith('L'): return 'Upah'
                if c.startswith('M'): return 'Bahan'
                if c.startswith('E'): return 'Alat'
                return 'Lainnya'
            
            df_clean['Kategori'] = df_clean['Kode'].apply(get_category)
            
            st.session_state.db_prices = df_clean
            return len(df_clean)
        except Exception as e:
            st.error(f"Gagal memproses file Harga Dasar: {e}")
            return 0

    def load_analysis_file(self, file_obj, division_name):
        """
        Parser Cerdas untuk file Analisis (Beton, Galian, dll).[1, 1]
        Menggunakan logika State Machine untuk mendeteksi struktur hierarkis.
        """
        try:
            df = pd.read_csv(file_obj, header=None)
            
            current_item_code = None
            current_item_desc = None
            current_section = None # 'Upah', 'Bahan', 'Alat'
            
            # Pola Regex untuk mendeteksi Kode Analisa (misal: 2.2.1.1, A.2.2.1)
            code_pattern = re.compile(r'^[\dA-Z]+\.[\d\.]+[a-zA-Z]?$')
            
            items_found = 0
            
            for _, row in df.iterrows():
                # Ekstraksi kolom dengan penanganan nilai kosong
                c1 = str(row).strip() if pd.notna(row) else "" # Potensi Kode
                c2 = str(row).strip() if pd.notna(row) else "" # Potensi Kode/Deskripsi
                c3 = str(row).strip() if pd.notna(row) else "" # Potensi Deskripsi/Satuan
                c5 = row # Biasanya letak Koefisien 
                
                # --- LOGIKA DETEKSI HEADER PEKERJAAN ---
                # Cek Kolom 1 atau Kolom 2 untuk pola kode
                detected_code = None
                detected_desc = None
                
                if code_pattern.match(c1) and len(c2) > 5:
                    detected_code = c1
                    detected_desc = c2
                elif code_pattern.match(c2) and len(c3) > 5:
                    detected_code = c2
                    detected_desc = c3
                
                if detected_code:
                    # Inisialisasi Item Baru dalam Database
                    current_item_code = detected_code
                    current_item_desc = detected_desc
                    st.session_state.db_analysis[current_item_code] = {
                        'deskripsi': current_item_desc,
                        'divisi': division_name,
                        'komponen':
                    }
                    items_found += 1
                    continue # Lanjut ke baris berikutnya

                # --- LOGIKA DETEKSI SEKSI SUMBER DAYA ---
                # Mendeteksi baris pemisah "A. TENAGA", "B. BAHAN"
                row_text = " ".join([str(x) for x in row.values]).upper()
                if 'TENAGA KERJA' in row_text:
                    current_section = 'Upah'
                    continue
                elif 'BAHAN' in row_text:
                    current_section = 'Bahan'
                    continue
                elif 'PERALATAN' in row_text:
                    current_section = 'Alat'
                    continue

                # --- LOGIKA EKSTRAKSI KOMPONEN ---
                # Baris komponen valid harus memiliki koefisien numerik
                coef = clean_coefficient(c5)
                if current_item_code and current_section and coef > 0:
                    # Nama komponen biasanya di kolom 2 atau 3
                    # Prioritaskan kolom yang memiliki teks panjang
                    comp_name = c2 if len(c2) > 3 else c3
                    
                    st.session_state.db_analysis[current_item_code]['komponen'].append({
                        'nama': comp_name,
                        'nama_norm': normalize_text(comp_name),
                        'tipe': current_section,
                        'koefisien': coef,
                        'satuan': str(row) if pd.notna(row) else ''
                    })
            
            return items_found
        except Exception as e:
            st.error(f"Gagal memproses file {division_name}: {e}")
            return 0

# ==========================================
# 3. CORE CALCULATION ENGINE
# ==========================================
def calculate_catalog_prices():
    """
    Menghitung Harga Satuan Jadi untuk setiap item analisis.
    Melakukan 'Linking' antara Analisis dan Harga Dasar.
    """
    if not st.session_state.db_analysis or st.session_state.db_prices.empty:
        return pd.DataFrame()

    # 1. Buat Lookup Dictionary untuk kecepatan akses O(1)
    # Mapping: Nama Normalisasi -> Harga
    price_map = dict(zip(
        st.session_state.db_prices['Uraian_Norm'], 
        st.session_state.db_prices['Harga']
    ))
    
    catalog_data =
    
    # 2. Iterasi setiap item pekerjaan (Analisa)
    for code, item in st.session_state.db_analysis.items():
        biaya_upah = 0
        biaya_bahan = 0
        biaya_alat = 0
        
        detail_components = # Untuk audit trail
        
        for comp in item['komponen']:
            c_name = comp['nama_norm']
            unit_price = 0
            match_type = "None"
            
            # --- STRATEGI PENCOCOKAN HARGA (FUZZY LOGIC SEDERHANA) ---
            # A. Pencocokan Eksak
            if c_name in price_map:
                unit_price = price_map[c_name]
                match_type = "Exact"
            else:
                # B. Pencocokan Parsial (Fallback)
                # Contoh: "Semen" di Analisa vs "Semen Portland (PC)" di Harga
                # Kita cari apakah ada key di price_map yang mengandung kata kunci komponen
                # Ini mahal secara komputasi, tapi diperlukan untuk data SNI yang tidak bersih
                for k, v in price_map.items():
                    # Jika nama komponen (misal: "batu kali") ada di dalam nama harga ("batu kali belah")
                    if c_name in k or k in c_name:
                        unit_price = v
                        match_type = "Partial"
                        break
            
            subtotal = unit_price * comp['koefisien']
            
            # Akumulasi berdasarkan kategori
            if comp['tipe'] == 'Upah': biaya_upah += subtotal
            elif comp['tipe'] == 'Bahan': biaya_bahan += subtotal
            elif comp['tipe'] == 'Alat': biaya_alat += subtotal
            
            detail_components.append(f"{comp['nama']} ({match_type})")

        # Hitung Overhead dan Total
        total_dasar = biaya_upah + biaya_bahan + biaya_alat
        overhead_pct = st.session_state.get('overhead_pct', 15.0) / 100
        nilai_overhead = total_dasar * overhead_pct
        harga_final = total_dasar + nilai_overhead
        
        catalog_data.append({
            'Kode': code,
            'Uraian': item['deskripsi'],
            'Divisi': item['divisi'],
            'Biaya_Upah': biaya_upah,
            'Biaya_Bahan': biaya_bahan,
            'Biaya_Alat': biaya_alat,
            'Total_Dasar': total_dasar,
            'Overhead': nilai_overhead,
            'Harga_Satuan': harga_final,
            # Metadata untuk debugging
            'Components_Count': len(item['komponen'])
        })
        
    return pd.DataFrame(catalog_data)

# ==========================================
# 4. USER INTERFACE (STREAMLIT LAYOUT)
# ==========================================
def main():
    # --- SIDEBAR: PENGATURAN & DATA ---
    st.sidebar.title("🔧 Data & Parameter")
    
    st.sidebar.subheader("1. Database Harga Dasar")
    f_price = st.sidebar.file_uploader("Upload 'Upah Bahan.csv'", type='csv', key='upl_price')
    if f_price:
        dm = AHSPDataManager()
        count = dm.load_basic_prices(f_price)
        st.sidebar.success(f"✅ {count} item harga dasar dimuat.")
        
    st.sidebar.subheader("2. Database Analisis (AHSP)")
    f_analysis = st.sidebar.file_uploader("Upload File Divisi (Beton, dll)", type='csv', accept_multiple_files=True, key='upl_analisa')
    if f_analysis:
        dm = AHSPDataManager()
        total_items = 0
        for f in f_analysis:
            # Gunakan nama file sebagai nama divisi
            div_name = f.name.replace('.csv', '').replace('_', ' ').title()
            count = dm.load_analysis_file(f, div_name)
            total_items += count
        st.sidebar.success(f"✅ {total_items} analisis pekerjaan dimuat.")
    
    st.sidebar.divider()
    st.session_state.overhead_pct = st.sidebar.slider("Margin Overhead & Profit (%)", 0, 25, 15)
    st.session_state.ppn_pct = st.sidebar.number_input("PPN (%)", 11.0)

    # --- MAIN AREA ---
    st.title("🏗️ SmartRAB-SNI v2.0")
    st.markdown("""
    **Sistem Estimasi Biaya Konstruksi Terintegrasi (SE Bina Konstruksi No. 30/2025)**
    *Fitur: Dynamic Parsing, Auto-Calculation, S-Curve Generation.*
    """)

    # Inisialisasi RAB DataFrame jika kosong
    if 'df_rab' not in st.session_state:
        st.session_state.df_rab = pd.DataFrame(columns=)

    # TABS UTAMA
    tab1, tab2, tab3 = st.tabs()

    # === TAB 1: KATALOG & PEMILIHAN ===
    with tab1:
        st.subheader("Katalog Analisis Harga Satuan")
        
        # Kalkulasi Ulang Harga setiap kali tab dibuka (Reaktif terhadap perubahan Overhead)
        df_catalog = calculate_catalog_prices()
        
        if df_catalog.empty:
            st.info("👋 Silakan upload file CSV 'Upah Bahan' dan 'Analisis' di Sidebar untuk memulai.")
        else:
            # Filter Divisi
            divisi_list = + sorted(list(df_catalog.unique()))
            selected_div = st.selectbox("Filter Divisi Pekerjaan:", divisi_list)
            
            if selected_div!= "Semua":
                df_display = df_catalog == selected_div]
            else:
                df_display = df_catalog
            
            st.dataframe(
                df_display], 
                use_container_width=True,
                column_config={"Harga_Satuan": st.column_config.NumberColumn(format="Rp %d")}
            )
            
            st.divider()
            st.subheader("➕ Tambah Item ke Proyek")
            
            # Form Input Item
            c1, c2 = st.columns()
            with c1:
                # Dropdown dengan Search
                # Format Label: Nama Pekerjaan - Rp Harga
                df_display['Label'] = df_display.apply(
                    lambda x: f"[{x['Kode']}] {x['Uraian']} - Rp {x:,.0f}", axis=1
                )
                selected_item_label = st.selectbox("Pilih Item Pekerjaan:", df_display['Label'].unique())
            
            with c2:
                vol_input = st.number_input("Volume", min_value=0.1, value=1.0)
            
            c3, c4 = st.columns(2)
            with c3:
                dur_input = st.number_input("Durasi (Minggu)", min_value=1, value=1)
            with c4:
                start_input = st.number_input("Minggu Ke- (Mulai)", min_value=1, value=1)
                
            if st.button("Masukkan ke RAB"):
                # Ambil data lengkap item yang dipilih
                item_data = df_display[df_display['Label'] == selected_item_label].iloc
                
                new_row = {
                    'Kode': item_data['Kode'],
                    'Uraian': item_data['Uraian'],
                    'Volume': vol_input,
                    'Satuan': 'Ls/Unit', # Idealnya diparsing juga
                    'Harga_Satuan': item_data,
                    'Total_Harga': vol_input * item_data,
                    'Durasi_Minggu': int(dur_input),
                    'Minggu_Mulai': int(start_input)
                }
                
                st.session_state.df_rab = pd.concat(
                   )], 
                    ignore_index=True
                )
                st.success(f"Sukses menambahkan: {item_data['Uraian']}")

    # === TAB 2: RAB PROYEK ===
    with tab2:
        st.subheader("Rencana Anggaran Biaya (RAB)")
        
        if not st.session_state.df_rab.empty:
            # Data Editor memungkinkan user mengubah volume langsung di tabel
            edited_df = st.data_editor(
                st.session_state.df_rab,
                column_config={
                    "Total_Harga": st.column_config.NumberColumn(format="Rp %d", disabled=True),
                    "Harga_Satuan": st.column_config.NumberColumn(format="Rp %d", disabled=True),
                    "Volume": st.column_config.NumberColumn(required=True)
                },
                use_container_width=True,
                num_rows="dynamic"
            )
            
            # Update Session State jika ada edit
            # Recalculate Total jika volume berubah
            edited_df = edited_df['Volume'] * edited_df
            st.session_state.df_rab = edited_df
            
            # Rekapitulasi Akhir
            total_fisik = edited_df.sum()
            ppn_val = total_fisik * (st.session_state.ppn_pct / 100)
            grand_total = total_fisik + ppn_val
            
            st.divider()
            col_tot1, col_tot2 = st.columns(2)
            with col_tot1:
                st.markdown("### Total Biaya Fisik")
                st.markdown(f"# Rp {total_fisik:,.0f}")
            with col_tot2:
                st.markdown("### Grand Total (Inc. PPN)")
                st.markdown(f"# Rp {grand_total:,.0f}")
                
            # Download Button
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                edited_df.to_excel(writer, sheet_name='RAB', index=False)
            st.download_button(
                label="📥 Download Excel RAB",
                data=buffer,
                file_name="RAB_Proyek_SNI.xlsx",
                mime="application/vnd.ms-excel"
            )
        else:
            st.warning("RAB masih kosong. Silakan pilih item dari Tab Katalog.")

    # === TAB 3: KURVA S ===
    with tab3:
        st.subheader("Jadwal & Kurva S")
        
        if not st.session_state.df_rab.empty:
            df = st.session_state.df_rab.copy()
            total_rab = df.sum()
            
            if total_rab > 0:
                # 1. Hitung Bobot (%)
                df = (df / total_rab) * 100
                
                # 2. Tentukan Timeline Proyek
                max_week = int(df.apply(lambda x: x['Minggu_Mulai'] + x - 1, axis=1).max())
                weeks = list(range(1, max_week + 2))
                
                # 3. Distribusi Bobot per Minggu
                schedule_data = {w: 0.0 for w in weeks}
                
                for _, row in df.iterrows():
                    start = int(row['Minggu_Mulai'])
                    duration = int(row)
                    bobot_per_week = row / duration
                    
                    for w in range(start, start + duration):
                        if w in schedule_data:
                            schedule_data[w] += bobot_per_week
                
                # 4. Dataframe Kurva S
                df_curve = pd.DataFrame({
                    'Minggu': weeks,
                    'Rencana_Parsial': [schedule_data[w] for w in weeks]
                })
                df_curve = df_curve.cumsum()
                
                # 5. Visualisasi dengan Altair
                base = alt.Chart(df_curve).encode(x='Minggu:O')
                
                bar = base.mark_bar(opacity=0.3, color='blue').encode(
                    y=alt.Y('Rencana_Parsial', title='Bobot Mingguan (%)'),
                    tooltip=
                )
                
                line = base.mark_line(point=True, color='red').encode(
                    y=alt.Y('Rencana_Kumulatif', title='Bobot Kumulatif (%)'),
                    tooltip=
                )
                
                combo_chart = (bar + line).properties(height=400).interactive()
                
                st.altair_chart(combo_chart, use_container_width=True)
                
                with st.expander("Lihat Data Tabel Kurva S"):
                    st.dataframe(df_curve)
            else:
                st.error("Total RAB 0, tidak bisa membuat kurva.")
        else:
            st.info("Buat RAB terlebih dahulu untuk menjana Kurva S.")

if __name__ == "__main__":
    main()

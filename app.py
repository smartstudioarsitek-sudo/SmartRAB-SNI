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
    Membersihkan format mata uang/angka menjadi float.
    Mendukung format: Rp 1.000.000,00 atau 126000 (integer)
    """
    if pd.isna(val) or val == '':
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
        
    s = str(val).replace('Rp', '').replace(' ', '')
    # Jika ada titik ribuan dan koma desimal (format Indo)
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    # Jika hanya ada titik (mungkin ribuan atau desimal, asumsi ribuan jika > 3 digit)
    elif '.' in s and len(s.split('.')[-1]) == 3:
        s = s.replace('.', '')
    
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
    if isinstance(val, (int, float)):
        return float(val)
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
    return text.lower().strip().replace('"', '').replace("'", "").replace("  ", " ")

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
            st.session_state.db_analysis = {} 

    def load_basic_prices(self, file_obj):
        """
        Memproses file 'Upah Bahan.csv'.
        """
        try:
            # Membaca CSV tanpa header, karena struktur data agak berantakan di baris awal
            # Berdasarkan inspeksi file: Data dimulai efektif setelah baris header di index 5/6
            df = pd.read_csv(file_obj, header=None, skiprows=6)
            
            # Mapping kolom berdasarkan inspeksi struktur file aktual:
            # Col Index 4: Kode (L.01)
            # Col Index 5: Uraian (Pekerja)
            # Col Index 6: Satuan (OH)
            # Col Index 7: Harga (126000)
            
            # Pastikan file memiliki cukup kolom
            if df.shape[1] < 8:
                st.error("Format file Upah Bahan tidak sesuai (jumlah kolom kurang).")
                return 0

            df_clean = df.iloc[:, [4, 5, 6, 7]].copy()
            df_clean.columns = ['Kode', 'Uraian', 'Satuan', 'Harga']
            
            # Data Cleaning
            df_clean = df_clean.dropna(subset=['Uraian'])
            df_clean['Harga'] = df_clean['Harga'].apply(clean_currency_str)
            df_clean['Uraian_Norm'] = df_clean['Uraian'].apply(normalize_text)
            
            # Kategorisasi Otomatis berdasarkan Kode
            def get_category(code):
                c = str(code).upper()
                if pd.isna(c) or c == 'NAN': return 'Lainnya'
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
        Parser Cerdas untuk file Analisis (Beton, Galian, dll).
        Menggunakan logika kolom offset yang disesuaikan dengan file upload.
        """
        try:
            df = pd.read_csv(file_obj, header=None)
            
            current_item_code = None
            current_item_desc = None
            current_section = None # 'Upah', 'Bahan', 'Alat'
            
            # Regex: Kode Analisa (misal: 2.2.1.1, A.2.2.1, 10.1.1)
            # Membolehkan angka dan titik, serta huruf di depan opsional
            code_pattern = re.compile(r'^[A-Z]?\d+(\.\d+)+[a-zA-Z]?$')
            
            items_found = 0
            
            for _, row in df.iterrows():
                # Akses kolom dengan aman (handle jika kolom NaN)
                # Berdasarkan inspeksi file:
                # Col 2: Kode Analisa / No Urut Komponen
                # Col 3: Deskripsi Item / Nama Komponen
                # Col 5: Koefisien
                
                c2 = str(row[2]).strip() if pd.notna(row[2]) else "" # Potensi Kode Header
                c3 = str(row[3]).strip() if pd.notna(row[3]) else "" # Deskripsi / Nama Komponen
                c5_val = row[5] # Koefisien (raw)
                
                # --- LOGIKA DETEKSI HEADER PEKERJAAN ---
                detected_code = None
                
                # Jika Col 2 cocok pola kode analisa (misal 2.2.1.1) dan Deskripsi cukup panjang
                if code_pattern.match(c2) and len(c3) > 5:
                    detected_code = c2
                    detected_desc = c3
                
                if detected_code:
                    # Inisialisasi Item Baru
                    current_item_code = detected_code
                    current_item_desc = detected_desc
                    current_section = None # Reset section saat ganti item
                    st.session_state.db_analysis[current_item_code] = {
                        'deskripsi': current_item_desc,
                        'divisi': division_name,
                        'komponen': []
                    }
                    items_found += 1
                    continue 

                # --- LOGIKA DETEKSI SEKSI SUMBER DAYA ---
                # Menggabungkan seluruh text di baris untuk mencari keyword
                row_text = " ".join([str(x) for x in row.values if pd.notna(x)]).upper()
                
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
                coef = clean_coefficient(c5_val)
                if current_item_code and current_section and coef > 0:
                    # Nama komponen ada di Col 3
                    comp_name = c3
                    
                    # Validasi: Nama komponen tidak boleh kosong atau angka saja
                    if len(comp_name) > 2 and not comp_name.replace('.','').isdigit():
                        st.session_state.db_analysis[current_item_code]['komponen'].append({
                            'nama': comp_name,
                            'nama_norm': normalize_text(comp_name),
                            'tipe': current_section,
                            'koefisien': coef,
                            'satuan': str(row[4]) if pd.notna(row[4]) else '' # Col 4 biasanya satuan
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
    """
    if not st.session_state.db_analysis or st.session_state.db_prices.empty:
        return pd.DataFrame()

    # 1. Lookup Dictionary: Nama Normalisasi -> Harga
    price_map = dict(zip(
        st.session_state.db_prices['Uraian_Norm'], 
        st.session_state.db_prices['Harga']
    ))
    
    catalog_data = []
    
    # 2. Iterasi Analisa
    for code, item in st.session_state.db_analysis.items():
        biaya_upah = 0
        biaya_bahan = 0
        biaya_alat = 0
        
        for comp in item['komponen']:
            c_name = comp['nama_norm']
            unit_price = 0
            
            # --- STRATEGI PENCOCOKAN HARGA ---
            # A. Exact Match
            if c_name in price_map:
                unit_price = price_map[c_name]
            else:
                # B. Partial Match (Fallback)
                # Cari string yang mengandung kata kunci
                # Optimasi: Hanya cari jika panjang string cukup spesifik
                for k, v in price_map.items():
                    # Jika komponen terkandung dalam master harga (ex: "Semen" in "Semen Portland")
                    # ATAU master harga terkandung dalam komponen (ex: "Paku" in "Paku 5 cm")
                    if (len(c_name) > 3 and c_name in k) or (len(k) > 3 and k in c_name):
                        unit_price = v
                        break
            
            subtotal = unit_price * comp['koefisien']
            
            if comp['tipe'] == 'Upah': biaya_upah += subtotal
            elif comp['tipe'] == 'Bahan': biaya_bahan += subtotal
            elif comp['tipe'] == 'Alat': biaya_alat += subtotal
            
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
            'Harga_Satuan': harga_final
        })
        
    return pd.DataFrame(catalog_data)

# ==========================================
# 4. USER INTERFACE (STREAMLIT LAYOUT)
# ==========================================
def main():
    # --- SIDEBAR ---
    st.sidebar.title("🔧 Data & Parameter")
    
    st.sidebar.subheader("1. Database Harga Dasar")
    f_price = st.sidebar.file_uploader("Upload 'Upah Bahan.csv'", type='csv', key='upl_price')
    if f_price:
        dm = AHSPDataManager()
        count = dm.load_basic_prices(f_price)
        st.sidebar.success(f"✅ {count} item harga dasar dimuat.")
        
    st.sidebar.subheader("2. Database Analisis (AHSP)")
    f_analysis = st.sidebar.file_uploader("Upload File Divisi", type='csv', accept_multiple_files=True, key='upl_analisa')
    if f_analysis:
        dm = AHSPDataManager()
        total_items = 0
        for f in f_analysis:
            div_name = f.name.replace('.csv', '').replace('AHSP CIPTA KARYA SE BINA KONSTRUKSI NO 30.xlsx - ', '').strip()
            count = dm.load_analysis_file(f, div_name)
            total_items += count
        st.sidebar.success(f"✅ {total_items} analisis pekerjaan dimuat.")
    
    st.sidebar.divider()
    st.session_state.overhead_pct = st.sidebar.slider("Margin Overhead & Profit (%)", 0, 25, 15)
    st.session_state.ppn_pct = st.sidebar.number_input("PPN (%)", value=11.0)

    # --- MAIN AREA ---
    st.title("🏗️ SmartRAB-SNI v2.0")
    st.write("Sistem Estimasi Biaya Konstruksi Terintegrasi (SE Bina Konstruksi No. 30/2025)")

    if 'df_rab' not in st.session_state:
        st.session_state.df_rab = pd.DataFrame(columns=['Kode', 'Uraian', 'Volume', 'Satuan', 'Harga_Satuan', 'Total_Harga', 'Durasi_Minggu', 'Minggu_Mulai'])

    tab1, tab2, tab3 = st.tabs(["📚 Katalog Analisa", "💰 RAB Proyek", "📈 Jadwal & Kurva S"])

    # === TAB 1: KATALOG ===
    with tab1:
        st.subheader("Katalog Analisis Harga Satuan")
        df_catalog = calculate_catalog_prices()
        
        if df_catalog.empty:
            st.info("Silakan upload file CSV di sidebar.")
        else:
            divisi_list = ["Semua"] + sorted(list(df_catalog['Divisi'].unique()))
            selected_div = st.selectbox("Filter Divisi:", divisi_list)
            
            if selected_div != "Semua":
                df_display = df_catalog[df_catalog['Divisi'] == selected_div]
            else:
                df_display = df_catalog
            
            st.dataframe(
                df_display[['Kode', 'Uraian', 'Harga_Satuan', 'Total_Dasar', 'Overhead']], 
                use_container_width=True,
                column_config={"Harga_Satuan": st.column_config.NumberColumn(format="Rp %d")}
            )
            
            st.divider()
            st.write("### Tambah Item ke RAB")
            c1, c2 = st.columns([3, 1])
            with c1:
                df_display['Label'] = df_display.apply(lambda x: f"[{x['Kode']}] {x['Uraian']} - Rp {x['Harga_Satuan']:,.0f}", axis=1)
                selected_item_label = st.selectbox("Pilih Item:", df_display['Label'].unique())
            with c2:
                vol_input = st.number_input("Volume", min_value=0.1, value=1.0)
            
            c3, c4 = st.columns(2)
            with c3:
                dur_input = st.number_input("Durasi (Minggu)", min_value=1, value=1)
            with c4:
                start_input = st.number_input("Minggu Mulai", min_value=1, value=1)
                
            if st.button("➕ Masukkan ke RAB"):
                item_data = df_display[df_display['Label'] == selected_item_label].iloc[0]
                new_row = pd.DataFrame([{
                    'Kode': item_data['Kode'],
                    'Uraian': item_data['Uraian'],
                    'Volume': vol_input,
                    'Satuan': 'Ls/Unit',
                    'Harga_Satuan': item_data['Harga_Satuan'],
                    'Total_Harga': vol_input * item_data['Harga_Satuan'],
                    'Durasi_Minggu': int(dur_input),
                    'Minggu_Mulai': int(start_input)
                }])
                st.session_state.df_rab = pd.concat([st.session_state.df_rab, new_row], ignore_index=True)
                st.success("Item ditambahkan!")

    # === TAB 2: RAB ===
    with tab2:
        st.subheader("Rencana Anggaran Biaya")
        if not st.session_state.df_rab.empty:
            edited_df = st.data_editor(
                st.session_state.df_rab,
                column_config={
                    "Total_Harga": st.column_config.NumberColumn(format="Rp %d", disabled=True),
                    "Harga_Satuan": st.column_config.NumberColumn(format="Rp %d", disabled=True)
                },
                use_container_width=True,
                num_rows="dynamic"
            )
            
            # Recalculate Logic
            edited_df['Total_Harga'] = edited_df['Volume'] * edited_df['Harga_Satuan']
            st.session_state.df_rab = edited_df
            
            total_fisik = edited_df['Total_Harga'].sum()
            ppn_val = total_fisik * (st.session_state.ppn_pct / 100)
            grand_total = total_fisik + ppn_val
            
            st.metric("Total Biaya Fisik", f"Rp {total_fisik:,.0f}")
            st.metric("Grand Total (+PPN)", f"Rp {grand_total:,.0f}")
        else:
            st.warning("RAB Kosong.")

    # === TAB 3: KURVA S ===
    with tab3:
        st.subheader("Kurva S Proyek")
        if not st.session_state.df_rab.empty and st.session_state.df_rab['Total_Harga'].sum() > 0:
            df = st.session_state.df_rab.copy()
            total_rab = df['Total_Harga'].sum()
            
            max_week = int(df.apply(lambda x: x['Minggu_Mulai'] + x['Durasi_Minggu'] - 1, axis=1).max())
            weeks = list(range(1, max_week + 2))
            schedule_data = {w: 0.0 for w in weeks}
            
            for _, row in df.iterrows():
                start = int(row['Minggu_Mulai'])
                duration = int(row['Durasi_Minggu'])
                cost = row['Total_Harga']
                if duration > 0:
                    cost_per_week = cost / duration
                    weight_per_week = (cost_per_week / total_rab) * 100
                    for w in range(start, start + duration):
                        if w in schedule_data:
                            schedule_data[w] += weight_per_week
            
            df_curve = pd.DataFrame({
                'Minggu': weeks,
                'Bobot_Mingguan': [schedule_data[w] for w in weeks]
            })
            df_curve['Bobot_Kumulatif'] = df_curve['Bobot_Mingguan'].cumsum()
            
            base = alt.Chart(df_curve).encode(x='Minggu:O')
            bar = base.mark_bar(opacity=0.3).encode(y='Bobot_Mingguan', tooltip=['Minggu', 'Bobot_Mingguan'])
            line = base.mark_line(color='red', point=True).encode(y='Bobot_Kumulatif', tooltip=['Minggu', 'Bobot_Kumulatif'])
            
            st.altair_chart((bar + line).interactive(), use_container_width=True)
            st.dataframe(df_curve)

if __name__ == "__main__":
    main()

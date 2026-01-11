import streamlit as st
import pandas as pd
import io
import xlsxwriter
import altair as alt
import streamlit.components.v1 as components
import re

# ==========================================
# 0. HELPER FUNCTIONS (LOGIC BARU)
# ==========================================
def clean_currency(val):
    """Membersihkan format uang (Rp 1.000.000 -> 1000000)"""
    if pd.isna(val) or val == '': return 0.0
    s = str(val).replace('Rp', '').replace('.', '').replace(' ', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def normalize_text(text):
    """Normalisasi teks untuk pencocokan (lowercase, no simbol)"""
    if not isinstance(text, str): return ""
    return text.lower().strip().replace('"', '').replace("'", "")

# ==========================================
# 1. MODUL DATABASE AHSP (ADAPTIVE)
# ==========================================
def get_catalog_view():
    """
    Mengambil view gabungan untuk Sidebar.
    Kini dinamis: Mengambil dari hasil perhitungan sistem, bukan hardcoded list.
    """
    # Pastikan perhitungan sudah berjalan
    if 'df_analysis_detailed' not in st.session_state:
        calculate_system()
        
    df_det = st.session_state['df_analysis_detailed']
    
    # Grouping untuk mendapatkan harga final per item analisa
    # Mengambil Overhead Global dari session
    ov_factor = 1 + (st.session_state.get('global_overhead', 15.0) / 100)
    
    catalog = []
    
    # Ambil kode unik
    if not df_det.empty:
        unique_codes = df_det['Kode_Analisa'].unique()
        for code in unique_codes:
            # Ambil slice data untuk kode ini
            slice_data = df_det[df_det['Kode_Analisa'] == code]
            if slice_data.empty: continue
            
            # Ambil info header dari baris pertama
            first_row = slice_data.iloc[0]
            desc = first_row['Uraian_Pekerjaan']
            
            # Hitung total dasar
            total_dasar = slice_data['Subtotal'].sum()
            final_price = total_dasar * ov_factor
            
            # Tentukan kategori (Divisi) - Logika sederhana berdasarkan kode atau default
            # Di kode asli hardcoded, disini kita coba mapping sederhana
            category = "Pekerjaan Umum"
            if "Tanah" in desc: category = "Divisi 2: Tanah"
            elif "Pondasi" in desc or "Beton" in desc: category = "Divisi 3: Struktur"
            elif "Dinding" in desc or "Lantai" in desc: category = "Divisi 4: Arsitektur"
            elif "Pipa" in desc or "Kabel" in desc: category = "Divisi 5: MEP"
            else: category = "Divisi 1: Persiapan"

            catalog.append({
                "Category": category,
                "Item": desc,     # Nama Item (misal: Galian Tanah)
                "Unit": "Unit",   # Satuan default (bisa diperbaiki jika ada data satuan pekerjaan)
                "Price": final_price,
                "Kode_Ref": code
            })
            
    return pd.DataFrame(catalog)

# ==========================================
# 2. FUNGSI INJEKSI (SIDEBAR UI TETAP)
# ==========================================
def render_ahsp_selector():
    st.sidebar.markdown("---")
    st.sidebar.subheader("📚 Database AHSP (Cipta Karya)")
    
    # UPDATE: Load data dinamis dari session state
    df_ahsp = get_catalog_view()
    
    if df_ahsp.empty:
        st.sidebar.warning("Database kosong. Harap Initialize Data.")
        return

    # 1. Dropdown Kategori
    kategori_list = df_ahsp['Category'].unique()
    # Handle jika kategori kosong
    if len(kategori_list) == 0:
        kategori_list = ["Umum"]
        df_ahsp['Category'] = "Umum"
        
    selected_category = st.sidebar.selectbox("Pilih Divisi Pekerjaan", kategori_list)
    
    # 2. Dropdown Item (Filter berdasarkan Kategori)
    filtered_items = df_ahsp[df_ahsp['Category'] == selected_category]
    
    # Buat label yang unik agar selectbox tidak error jika ada nama sama
    filtered_items['Label_View'] = filtered_items['Item']
    
    selected_item_name = st.sidebar.selectbox("Pilih Item Pekerjaan", filtered_items['Label_View'].unique())
    
    # Ambil detail item
    item_row = filtered_items[filtered_items['Label_View'] == selected_item_name].iloc[0]
    st.sidebar.info(f"Satuan: {item_row['Unit']} | Harga Estimasi: Rp {item_row['Price']:,.0f}")
    
    # 3. Input Parameter Proyek
    col_vol, col_dur = st.sidebar.columns(2)
    with col_vol:
        vol_input = st.number_input("Volume", min_value=1.0, value=10.0, step=1.0, key='vol_ahsp')
    with col_dur:
        dur_input = st.number_input("Durasi (Mg)", min_value=1, value=1, key='dur_ahsp')
    start_input = st.sidebar.number_input("Minggu Ke-", min_value=1, value=1, key='start_ahsp')

    # 4. Eksekusi Tombol Tambah
    if st.sidebar.button("➕ Masukkan ke RAB"):
        try:
            # Mengambil Kode Referensi dari item yang dipilih
            selected_code = item_row['Kode_Ref']
            
            # Update df_rab (Bill of Quantities)
            new_rab = {
                'No': len(st.session_state.df_rab) + 1,
                'Divisi': selected_category,
                'Uraian_Pekerjaan': selected_item_name,
                'Kode_Analisa_Ref': selected_code, # Gunakan Kode Relasi
                'Satuan_Pek': item_row['Unit'],
                'Volume': vol_input,
                'Harga_Satuan_Jadi': 0, # Nanti dihitung ulang system
                'Total_Harga': 0,       # Nanti dihitung ulang system
                'Bobot': 0,
                'Durasi_Minggu': dur_input,
                'Minggu_Mulai': start_input
            }
            st.session_state.df_rab = pd.concat([
                st.session_state.df_rab, 
                pd.DataFrame([new_rab])
            ], ignore_index=True)

            st.sidebar.success(f"Sukses! {selected_item_name} ditambahkan.")
            calculate_system() # Recalculate immediate
            st.rerun()

        except Exception as e:
            st.sidebar.error(f"Terjadi kesalahan: {e}")

# ==========================================
# KONFIGURASI HALAMAN
# ==========================================
st.set_page_config(page_title="SmartRAB-SNI", layout="wide")

# --- 1. Inisialisasi Data (VERSI ANTI-CRASH) ---
def initialize_data():
    defaults = {
        'global_overhead': 15.0,
        'project_name': '-',
        'project_loc': '-',
        'project_year': '2025'
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # SEED DATA: HARGA DASAR
    if 'df_prices' not in st.session_state:
        data_prices = {
            'Kode': ['M.01', 'M.02', 'M.03', 'M.04', 'L.01', 'L.02', 'L.03', 'L.04', 'E.01'],
            'Komponen': ['Semen Portland', 'Pasir Beton', 'Batu Kali', 'Paku', 'Pekerja', 'Tukang Batu', 'Kepala Tukang', 'Mandor', 'Sewa Molen'],
            'Satuan': ['kg', 'kg', 'm3', 'kg', 'OH', 'OH', 'OH', 'OH', 'Jam'],
            'Harga_Dasar': [1300, 300, 286500, 15000, 100000, 145000, 175000, 200000, 85000],
            'Kategori': ['Material', 'Material', 'Material', 'Material', 'Upah', 'Upah', 'Upah', 'Upah', 'Alat']
        }
        st.session_state['df_prices'] = pd.DataFrame(data_prices)

    # SEED DATA: ANALISA
    if 'df_analysis' not in st.session_state:
        data_analysis = {
            'Kode_Analisa': [
                'A.1.1', 'A.1.1', 'A.1.1',
                'A.2.1', 'A.2.1',
                'A.3.1', 'A.3.1', 'A.3.1', 'A.3.1', 'A.3.1',
                'A.4.1', 'A.4.1', 'A.4.1', 'A.4.1'
            ],
            'Uraian_Pekerjaan': [
                'Pagar Sementara Kayu (Tinggi 2m)', 'Pagar Sementara Kayu (Tinggi 2m)', 'Pagar Sementara Kayu (Tinggi 2m)',
                'Galian Tanah Biasa (Manual)', 'Galian Tanah Biasa (Manual)',
                'Pondasi Batu Belah 1:4', 'Pondasi Batu Belah 1:4', 'Pondasi Batu Belah 1:4', 'Pondasi Batu Belah 1:4', 'Pondasi Batu Belah 1:4',
                'Pasangan Dinding Bata Merah', 'Pasangan Dinding Bata Merah', 'Pasangan Dinding Bata Merah', 'Pasangan Dinding Bata Merah'
            ],
            'Komponen': [
                'Kayu Balok', 'Paku', 'Pekerja', 
                'Pekerja', 'Mandor', 
                'Batu Kali', 'Semen Portland', 'Pasir Beton', 'Pekerja', 'Tukang Batu', 
                'Bata Merah', 'Semen Portland', 'Pasir Pasang', 'Pekerja' 
            ],
            'Koefisien': [
                0.5, 0.1, 0.4, 
                0.75, 0.025, 
                1.2, 163.0, 0.52, 1.5, 0.75, 
                70.0, 11.5, 0.04, 0.3 
            ]
        }
        st.session_state['df_analysis'] = pd.DataFrame(data_analysis)

    # SEED DATA: RAB (Default jika kosong)
    if 'df_rab' not in st.session_state:
        data_rab = {
            'No': [1],
            'Divisi': ['PEKERJAAN STRUKTUR BAWAH'], 
            'Uraian_Pekerjaan': ['Pondasi Batu Belah 1:4'],
            'Kode_Analisa_Ref': ['A.3.1'],
            'Satuan_Pek': ['m3'],
            'Volume': [50.0],
            'Harga_Satuan_Jadi': [0.0],
            'Total_Harga': [0.0],
            'Durasi_Minggu': [2],
            'Minggu_Mulai': [1]
        }
        st.session_state['df_rab'] = pd.DataFrame(data_rab)
    
    # --- PERBAIKAN CRASH: Pastikan Kolom Kunci Selalu Ada ---
    # Ini mencegah KeyError jika sisa cache sesi sebelumnya rusak
    required_cols = ['Kode_Analisa_Ref', 'Durasi_Minggu', 'Minggu_Mulai']
    for col in required_cols:
        if col not in st.session_state['df_rab'].columns:
            if col == 'Kode_Analisa_Ref':
                st.session_state['df_rab'][col] = '' # Isi string kosong agar astype(str) tidak error
            else:
                st.session_state['df_rab'][col] = 1 # Default angka
        
    calculate_system()
# --- 2. Mesin Logika Utama (SMART MATCHING UPGRADE) ---
def calculate_system():
    df_p = st.session_state['df_prices'].copy()
    df_a = st.session_state['df_analysis'].copy()
    df_r = st.session_state['df_rab'].copy()
    
    overhead_pct = st.session_state.get('global_overhead', 15.0)
    overhead_factor = 1 + (overhead_pct / 100)

    # --- LOGIC BARU: FUZZY MATCHING & DATA CLEANING ---
    # 1. Normalisasi Key di kedua sisi
    df_p['Key'] = df_p['Komponen'].apply(normalize_text)
    df_a['Key_Raw'] = df_a['Komponen'].apply(normalize_text)
    
    # 2. Buat Dictionary Harga untuk Lookup Cepat
    price_dict = dict(zip(df_p['Key'], df_p['Harga_Dasar']))
    satuan_dict = dict(zip(df_p['Key'], df_p['Satuan']))
    kategori_dict = dict(zip(df_p['Key'], df_p['Kategori']))
    
    # 3. Fungsi Pencarian Cerdas
    def find_best_price(key_search):
        # A. Cek Exact Match
        if key_search in price_dict:
            return price_dict[key_search], satuan_dict.get(key_search, '-'), kategori_dict.get(key_search, 'Material')
            
        # B. Cek Partial Match (Misal "Semen" match dengan "Semen Portland")
        for k_db, price in price_dict.items():
            if key_search in k_db or k_db in key_search:
                return price, satuan_dict.get(k_db, '-'), kategori_dict.get(k_db, 'Material')
        
        return 0.0, '-', 'Material' # Not Found

    # 4. Terapkan ke DataFrame Analisa
    results = df_a['Key_Raw'].apply(find_best_price)
    
    # Unpack hasil tuple ke kolom baru
    df_a['Harga_Dasar'] = [res[0] for res in results]
    df_a['Satuan'] = [res[1] for res in results]
    df_a['Kategori'] = [res[2] for res in results]
    
    df_a['Subtotal'] = df_a['Koefisien'] * df_a['Harga_Dasar']
    
    st.session_state['df_analysis_detailed'] = df_a

    # 5. Hitung Harga Satuan Jadi per Kode Analisa
    unit_prices_pure = df_a.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices_pure['Harga_Kalkulasi'] = unit_prices_pure['Subtotal'] * overhead_factor 
    
    # Samakan Tipe Data
    df_r['Kode_Analisa_Ref'] = df_r['Kode_Analisa_Ref'].astype(str).str.strip()
    unit_prices_pure['Kode_Analisa'] = unit_prices_pure['Kode_Analisa'].astype(str).str.strip()

    # 6. Update RAB (Link Harga)
    df_r_temp = pd.merge(df_r, unit_prices_pure[['Kode_Analisa', 'Harga_Kalkulasi']], left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
    df_r['Harga_Satuan_Jadi'] = df_r_temp['Harga_Kalkulasi'].fillna(0)
    df_r['Total_Harga'] = df_r['Volume'] * df_r['Harga_Satuan_Jadi']
    st.session_state['df_rab'] = df_r

    # 7. Hitung Rekap Material
    material_breakdown = pd.merge(
        df_r[['Kode_Analisa_Ref', 'Volume']], 
        df_a[['Kode_Analisa', 'Komponen', 'Satuan', 'Koefisien', 'Harga_Dasar']], 
        left_on='Kode_Analisa_Ref', 
        right_on='Kode_Analisa', 
        how='left'
    )
    material_breakdown['Total_Kebutuhan_Material'] = material_breakdown['Volume'] * material_breakdown['Koefisien']
    material_breakdown['Total_Biaya_Material'] = material_breakdown['Total_Kebutuhan_Material'] * material_breakdown['Harga_Dasar']
    
    rekap_final = material_breakdown.groupby(['Komponen', 'Satuan']).agg({
        'Total_Kebutuhan_Material': 'sum',
        'Total_Biaya_Material': 'sum'
    }).reset_index()
    
    st.session_state['df_material_rekap'] = rekap_final

# --- 3. Logic Kurva S ---
def generate_s_curve_data():
    df = st.session_state['df_rab'].copy()
    grand_total = df['Total_Harga'].sum()
    
    if grand_total == 0:
        return None, None

    df['Bobot_Pct'] = (df['Total_Harga'] / grand_total) * 100
    
    max_week = int(df.apply(lambda x: x['Minggu_Mulai'] + x['Durasi_Minggu'] - 1, axis=1).max())
    if pd.isna(max_week) or max_week < 1: max_week = 1
    
    cumulative_list = []
    cumulative_progress = 0
    
    for w in range(1, max_week + 2):
        weekly_weight = 0
        for _, row in df.iterrows():
            start = row['Minggu_Mulai']
            duration = row['Durasi_Minggu']
            end = start + duration - 1
            if start <= w <= end:
                weekly_weight += (row['Bobot_Pct'] / duration)
        
        cumulative_progress += weekly_weight
        if cumulative_progress > 100: cumulative_progress = 100
        
        cumulative_list.append({
            'Minggu': f"M{w}",
            'Minggu_Int': w,
            'Rencana_Kumulatif': cumulative_progress
        })

    return df, pd.DataFrame(cumulative_list)

# --- 4. Helper UI Components & Printing ---

def render_print_style():
    st.markdown("""
        <style>
            @media print {
                [data-testid="stHeader"], 
                [data-testid="stSidebar"], 
                [data-testid="stToolbar"], 
                footer, 
                .stDeployButton { display: none !important; }
                .main .block-container { max-width: 100% !important; padding: 1rem !important; box-shadow: none !important; }
                body { background-color: white !important; color: black !important; }
            }
        </style>
    """, unsafe_allow_html=True)

def render_print_button():
    components.html(
        """
        <script>
            function cetak() { window.parent.print(); }
        </script>
        <div style="text-align: right;">
            <button onclick="cetak()" style="
                background-color: #f0f2f6; 
                border: 1px solid #ccc; 
                padding: 8px 16px; 
                border-radius: 4px; 
                cursor: pointer; 
                font-weight: bold;
                color: #333;
                font-family: sans-serif;">
                🖨️ Cetak Halaman / Print
            </button>
        </div>
        """,
        height=60
    )

def render_project_identity():
    st.markdown(f"""
    <div style="margin-bottom: 20px; font-family: sans-serif;">
        <table style="width:100%; border:none;">
            <tr><td style="font-weight:bold; width:150px;">PEKERJAAN</td><td>: {st.session_state['project_name']}</td></tr>
            <tr><td style="font-weight:bold;">LOKASI</td><td>: {st.session_state['project_loc']}</td></tr>
            <tr><td style="font-weight:bold;">TAHUN</td><td>: {st.session_state['project_year']}</td></tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

def render_footer():
    st.markdown("---")
    st.markdown("""
    <div style="text-align: right; color: red; font-size: 14px; font-weight: bold;">
        by SmartStudio, email smartstudioarsitek@gmail.com
    </div>
    """, unsafe_allow_html=True)

def to_excel_download(df, sheet_name="Sheet1"):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name=sheet_name)
    writer.close()
    return output.getvalue()

def generate_excel_template(data_dict, sheet_name):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df = pd.DataFrame(data_dict)
    df.to_excel(writer, index=False, sheet_name=sheet_name)
    writer.close()
    return output.getvalue()

def generate_rekap_final_excel(df_rekap, ppn_pct, pt_name, signer, position):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    workbook = writer.book
    worksheet = workbook.add_worksheet('Rekapitulasi')

    fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D3D3D3'})
    fmt_currency = workbook.add_format({'num_format': '#,##0', 'border': 1})
    fmt_text = workbook.add_format({'border': 1})
    fmt_bold = workbook.add_format({'bold': True, 'border': 1})
    
    worksheet.write(0, 0, "PEKERJAAN", fmt_bold)
    worksheet.write(0, 1, st.session_state['project_name'])
    worksheet.write(1, 0, "LOKASI", fmt_bold)
    worksheet.write(1, 1, st.session_state['project_loc'])
    worksheet.write(2, 0, "TAHUN", fmt_bold)
    worksheet.write(2, 1, st.session_state['project_year'])

    worksheet.merge_range('A5:C5', 'REKAPITULASI BIAYA', workbook.add_format({'bold': True, 'align': 'center', 'font_size': 14}))
    worksheet.merge_range('A6:C6', 'ENGINEERING ESTIMATE', workbook.add_format({'bold': True, 'align': 'center'}))
    
    worksheet.write(8, 0, 'No', fmt_header)
    worksheet.write(8, 1, 'URAIAN PEKERJAAN', fmt_header)
    worksheet.write(8, 2, 'TOTAL (Rp)', fmt_header)
    
    row = 9
    total_biaya = 0
    for idx, r in df_rekap.iterrows():
        worksheet.write(row, 0, chr(65+idx), fmt_text) 
        worksheet.write(row, 1, r['Divisi'], fmt_text)
        worksheet.write(row, 2, r['Total_Harga'], fmt_currency)
        total_biaya += r['Total_Harga']
        row += 1
        
    ppn_val = total_biaya * (ppn_pct/100)
    grand_total = total_biaya + ppn_val
    
    worksheet.write(row, 1, 'TOTAL BIAYA', fmt_bold)
    worksheet.write(row, 2, total_biaya, fmt_currency)
    row += 1
    worksheet.write(row, 1, f'PPN {ppn_pct}%', fmt_bold)
    worksheet.write(row, 2, ppn_val, fmt_currency)
    row += 1
    worksheet.write(row, 1, 'TOTAL', fmt_bold)
    worksheet.write(row, 2, grand_total, fmt_currency)
    
    row += 3
    worksheet.write(row, 2, pt_name, workbook.add_format({'bold': True, 'align': 'center'}))
    row += 4
    worksheet.write(row, 2, signer, workbook.add_format({'bold': True, 'align': 'center', 'underline': True}))
    row += 1
    worksheet.write(row, 2, position, workbook.add_format({'align': 'center'}))

    worksheet.set_column(0, 0, 5)
    worksheet.set_column(1, 1, 40)
    worksheet.set_column(2, 2, 20)
    
    writer.close()
    return output.getvalue()

# --- FITUR UPDATE DATABASE (PARSING CSV SNI) ---
def parse_sni_csv_analysis(uploaded_file):
    """Membaca file CSV SNI Analisa dengan cerdas"""
    try:
        df = pd.read_csv(uploaded_file, header=None)
        new_analysis_data = []
        
        current_code = None
        current_desc = None
        
        # Pola Regex untuk Kode (misal A.2.2.1)
        code_pattern = re.compile(r'^[\dA-Z]+\.[\d\.]+[a-zA-Z]?$')

        for _, row in df.iterrows():
            c1 = str(row[0]).strip() if pd.notna(row[0]) else ""
            c2 = str(row[1]).strip() if pd.notna(row[1]) else ""
            c3 = str(row[2]).strip() if pd.notna(row[2]) else ""
            
            # Deteksi Header Pekerjaan
            if code_pattern.match(c1) and len(c2) > 5:
                current_code = c1
                current_desc = c2
                continue
            
            # Deteksi Baris Komponen (Punya Koefisien di kolom tertentu)
            # Biasanya di CSV SNI, kolom index 4 atau 5 adalah koefisien
            try:
                coef_val = row[4] # Asumsi kolom ke-5
                if isinstance(coef_val, (int, float)) or (isinstance(coef_val, str) and coef_val.replace('.', '', 1).isdigit()):
                     coef = float(coef_val)
                     if coef > 0 and current_code:
                         comp_name = c2 if len(c2) > 2 else c3
                         new_analysis_data.append({
                             'Kode_Analisa': current_code,
                             'Uraian_Pekerjaan': current_desc,
                             'Komponen': comp_name,
                             'Koefisien': coef
                         })
            except:
                pass
                
        if new_analysis_data:
            df_new = pd.DataFrame(new_analysis_data)
            # Gabungkan dengan data lama (Append)
            st.session_state['df_analysis'] = pd.concat([st.session_state['df_analysis'], df_new], ignore_index=True)
            calculate_system()
            st.success(f"Berhasil mengimpor {len(df_new)} baris analisa baru!")
        else:
            st.error("Format CSV tidak dikenali atau kosong.")
            
    except Exception as e:
        st.error(f"Gagal parsing CSV: {e}")

def load_excel_prices(uploaded_file):
    try:
        # Cek tipe file, jika CSV gunakan parser khusus, jika Excel standar
        if uploaded_file.name.endswith('.csv'):
             df_new = pd.read_csv(uploaded_file)
             # Mapping kolom CSV SNI umum ke format kita
             # Asumsi CSV punya header: Kode, Uraian, Satuan, Harga
             if 'Harga' in df_new.columns and 'Uraian' in df_new.columns:
                 df_formatted = pd.DataFrame({
                     'Kode': df_new.iloc[:,0], # Asumsi kolom pertama kode
                     'Komponen': df_new['Uraian'],
                     'Satuan': df_new.get('Satuan', 'Unit'),
                     'Harga_Dasar': df_new['Harga'].apply(clean_currency),
                     'Kategori': 'Material' # Default
                 })
                 st.session_state['df_prices'] = pd.concat([st.session_state['df_prices'], df_formatted], ignore_index=True)
                 st.success("Harga CSV berhasil di-merge!")
             else:
                 st.error("CSV harus punya kolom 'Uraian' dan 'Harga'")
        else:
            df_new = pd.read_excel(uploaded_file)
            required = ['Komponen', 'Harga_Dasar', 'Kategori'] 
            if not set(required).issubset(df_new.columns):
                st.error(f"Format Excel salah! Wajib ada kolom: {required}")
                return
            st.session_state['df_prices'] = df_new
            st.success("Harga berhasil diupdate!")
            
        calculate_system()
    except Exception as e:
        st.error(f"Gagal membaca file: {e}")

def load_excel_rab_volume(uploaded_file):
    try:
        df_new = pd.read_excel(uploaded_file)
        
        required = ['Divisi', 'Uraian_Pekerjaan', 'Kode_Analisa_Ref', 'Volume']
        if not set(required).issubset(df_new.columns):
            st.error(f"Format Excel salah! Wajib ada kolom: {required}")
            return
        
        df_new['Kode_Analisa_Ref'] = df_new['Kode_Analisa_Ref'].astype(str).str.strip()
        
        df_clean = df_new[required].copy()
        df_clean['No'] = range(1, len(df_clean) + 1)
        df_clean['Satuan_Pek'] = 'ls/m3/m2' 
        df_clean['Harga_Satuan_Jadi'] = 0
        df_clean['Total_Harga'] = 0
        df_clean['Durasi_Minggu'] = 1 
        df_clean['Minggu_Mulai'] = 1 
        
        st.session_state['df_rab'] = df_clean
        calculate_system()
        st.success("Volume RAB berhasil diimport!")
    except Exception as e:
        st.error(f"Gagal membaca file: {e}")

def render_sni_html(kode, uraian, df_part, overhead_pct):
    cat_map = {'Upah': 'TENAGA KERJA', 'Material': 'BAHAN', 'Alat': 'PERALATAN'}
    groups = {'Upah': [], 'Material': [], 'Alat': []}
    totals = {'Upah': 0, 'Material': 0, 'Alat': 0}
    
    for _, row in df_part.iterrows():
        cat = row['Kategori']
        if cat not in groups: cat = 'Material'
        groups[cat].append(row)
        totals[cat] += row['Subtotal']

    html = f"""<div style="font-family: Arial, sans-serif; font-size: 14px; color: black;">
    <div style="background-color: #d1d1d1; padding: 10px; border: 1px solid black; font-weight: bold;">ANALISA HARGA SATUAN PEKERJAAN (AHSP) <br>{kode} - {uraian}</div>
    <table style="width:100%; border-collapse: collapse; border: 1px solid black;">
    <thead><tr style="background-color: #f0f0f0; text-align: center;">
    <th style="border: 1px solid black; padding: 5px; width: 5%;">No</th>
    <th style="border: 1px solid black; padding: 5px; width: 40%;">Uraian</th>
    <th style="border: 1px solid black; padding: 5px; width: 10%;">Satuan</th>
    <th style="border: 1px solid black; padding: 5px; width: 10%;">Koefisien</th>
    <th style="border: 1px solid black; padding: 5px; width: 15%;">Harga Satuan (Rp)</th>
    <th style="border: 1px solid black; padding: 5px; width: 20%;">Jumlah Harga (Rp)</th>
    </tr></thead><tbody>"""
    
    sections = [('A', 'Upah'), ('B', 'Material'), ('C', 'Alat')]
    
    for label, key in sections:
        items = groups[key]
        sni_label = cat_map[key]
        
        html += f"""<tr style="font-weight: bold; background-color: #fafafa;"><td style="border: 1px solid black; padding: 5px; text-align: center;">{label}</td><td colspan="5" style="border: 1px solid black; padding: 5px;">{sni_label}</td></tr>"""
        
        if not items:
            html += f"""<tr><td colspan="6" style="border: 1px solid black; padding: 5px; text-align: center; color: #888;">- Tidak ada komponen -</td></tr>"""
        else:
            for idx, item in enumerate(items):
                html += f"""<tr>
                <td style="border: 1px solid black; padding: 5px; text-align: center;">{idx+1}</td>
                <td style="border: 1px solid black; padding: 5px;">{item['Komponen']}</td>
                <td style="border: 1px solid black; padding: 5px; text-align: center;">{item['Satuan']}</td>
                <td style="border: 1px solid black; padding: 5px; text-align: center;">{item['Koefisien']:.4f}</td>
                <td style="border: 1px solid black; padding: 5px; text-align: right;">{item['Harga_Dasar']:,.2f}</td>
                <td style="border: 1px solid black; padding: 5px; text-align: right;">{item['Subtotal']:,.2f}</td>
                </tr>"""
        
        html += f"""<tr style="font-weight: bold;"><td colspan="5" style="border: 1px solid black; padding: 5px; text-align: right;">JUMLAH HARGA {sni_label}</td><td style="border: 1px solid black; padding: 5px; text-align: right;">{totals[key]:,.2f}</td></tr>"""
        
    total_abc = totals['Upah'] + totals['Material'] + totals['Alat']
    overhead_val = total_abc * (overhead_pct / 100)
    final_price = total_abc + overhead_val
    
    html += f"""<tr style="background-color: #f9f9f9;"><td style="border: 1px solid black; padding: 5px; text-align: center; font-weight: bold;">D</td><td colspan="4" style="border: 1px solid black; padding: 5px; font-weight: bold;">JUMLAH (A+B+C)</td><td style="border: 1px solid black; padding: 5px; text-align: right; font-weight: bold;">{total_abc:,.2f}</td></tr>
    <tr><td style="border: 1px solid black; padding: 5px; text-align: center; font-weight: bold;">E</td><td colspan="4" style="border: 1px solid black; padding: 5px; font-weight: bold;">Biaya Umum dan Keuntungan (Overhead) {overhead_pct}% x D</td><td style="border: 1px solid black; padding: 5px; text-align: right; font-weight: bold;">{overhead_val:,.2f}</td></tr>
    <tr style="background-color: #d1d1d1; font-size: 16px;"><td style="border: 1px solid black; padding: 5px; text-align: center; font-weight: bold;">F</td><td colspan="4" style="border: 1px solid black; padding: 5px; font-weight: bold;">HARGA SATUAN PEKERJAAN (D+E)</td><td style="border: 1px solid black; padding: 5px; text-align: right; font-weight: bold;">{final_price:,.2f}</td></tr>
    </tbody></table></div>"""
    return html

# --- 5. Main UI ---
def main():
    initialize_data()
    render_print_style()
    render_ahsp_selector() # Sidebar
    
    st.title("🏗️ SmartRAB-SNI")
    st.caption("Sistem Integrated RAB & Material Control")
    
    tabs = st.tabs([
        "📊 1. REKAPITULASI", 
        "📝 2. RAB PROYEK", 
        "🔍 3. AHSP SNI", 
        "💰 4. HARGA SATUAN", 
        "🧱 5. REKAP MATERIAL",
        "📈 6. KURVA S"
    ])

    # === TAB 1: REKAPITULASI ===
    with tabs[0]:
        st.header("Rekapitulasi Biaya (Engineering Estimate)")
        render_print_button()
        col_main, col_set = st.columns([2, 1])
        
        with col_set:
            st.markdown("### ⚙️ Pengaturan & Identitas")
            st.markdown("**Identitas Proyek**")
            p_name = st.text_input("Nama Pekerjaan", value=st.session_state['project_name'])
            p_loc = st.text_input("Lokasi", value=st.session_state['project_loc'])
            p_year = st.text_input("Tahun Anggaran", value=st.session_state['project_year'])
            
            if p_name != st.session_state['project_name'] or p_loc != st.session_state['project_loc']:
                st.session_state['project_name'] = p_name
                st.session_state['project_loc'] = p_loc
                st.session_state['project_year'] = p_year
                st.rerun()

            st.write("---")
            new_overhead = st.number_input(
                "Margin Profit / Overhead (%)", 
                min_value=0.0, max_value=50.0, 
                value=st.session_state['global_overhead'], 
                step=0.5
            )
            if new_overhead != st.session_state['global_overhead']:
                st.session_state['global_overhead'] = new_overhead
                calculate_system()
                st.rerun()

            ppn_input = st.number_input("PPN (%)", value=11.0, step=1.0)
            pt_input = st.text_input("Nama Perusahaan", value="SMARTSTUDIIO")
            signer_input = st.text_input("Penandatangan", value="WARTO SANTOSO, ST")
            pos_input = st.text_input("Jabatan", value="LEADER")
        
        df_rab = st.session_state['df_rab']
        if 'Divisi' in df_rab.columns:
            rekap_divisi = df_rab.groupby('Divisi')['Total_Harga'].sum().reset_index()
        else:
            rekap_divisi = pd.DataFrame({'Divisi': ['Umum'], 'Total_Harga': [df_rab['Total_Harga'].sum()]})
            
        total_biaya = rekap_divisi['Total_Harga'].sum()
        ppn_val = total_biaya * (ppn_input / 100)
        grand_total_val = total_biaya + ppn_val
        
        with col_main:
            render_project_identity()
            st.markdown("### Tabel Rekapitulasi")
            st.dataframe(
                rekap_divisi, 
                use_container_width=True, 
                hide_index=True, 
                column_config={
                    "Divisi": st.column_config.TextColumn("URAIAN PEKERJAAN"),
                    "Total_Harga": st.column_config.NumberColumn("TOTAL (Rp)", format="Rp %d")
                }
            )
            st.markdown(f"""
            <div style="text-align: right; font-size: 16px; margin-top: 10px;">
                <b>TOTAL BIAYA : Rp {total_biaya:,.0f}</b><br>
                <b>PPN {ppn_input}% : Rp {ppn_val:,.0f}</b><br>
                <b style="font-size: 20px; color: blue;">TOTAL AKHIR : Rp {grand_total_val:,.0f}</b>
            </div>
            """, unsafe_allow_html=True)
        
        excel_rekap = generate_rekap_final_excel(rekap_divisi, ppn_input, pt_input, signer_input, pos_input)
        st.download_button("📥 Download Excel Laporan", excel_rekap, "1_Rekapitulasi_Biaya.xlsx")
        render_footer()

    # === TAB 2: RAB ===
    with tabs[1]:
        st.header("Rencana Anggaran Biaya")
        render_print_button()
        render_project_identity()

        # --- FITUR TAMBAH ITEM DARI DATABASE AHSP ---
        st.markdown("### ➕ Tambah Pekerjaan Baru")
        with st.container():
            df_analisa_ref = st.session_state['df_analysis'][['Kode_Analisa', 'Uraian_Pekerjaan']].drop_duplicates()
            ahsp_dict = dict(zip(df_analisa_ref['Kode_Analisa'], df_analisa_ref['Uraian_Pekerjaan']))
            
            c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
            with c1:
                pilihan_ahsp = st.selectbox(
                    "Pilih Item Pekerjaan (Database AHSP)", 
                    options=df_analisa_ref['Kode_Analisa'],
                    format_func=lambda x: f"{x} - {ahsp_dict.get(x, '')}"
                )
            with c2:
                last_divisi = "PEKERJAAN PERSIAPAN"
                if not st.session_state['df_rab'].empty:
                    last_divisi = st.session_state['df_rab']['Divisi'].iloc[-1]
                input_divisi = st.text_input("Kategori / Divisi", value=last_divisi)
            with c3:
                input_vol = st.number_input("Volume Awal", min_value=0.0, value=1.0, step=0.1)
            with c4:
                st.write("") 
                st.write("")
                btn_add = st.button("➕ Tambahkan", type="primary")

            if btn_add:
                uraian_fix = ahsp_dict.get(pilihan_ahsp, "Pekerjaan Baru")
                new_row = {
                    'No': len(st.session_state['df_rab']) + 1,
                    'Divisi': input_divisi,
                    'Uraian_Pekerjaan': uraian_fix,
                    'Kode_Analisa_Ref': pilihan_ahsp,
                    'Satuan_Pek': 'm3',
                    'Volume': input_vol,
                    'Harga_Satuan_Jadi': 0.0, 
                    'Total_Harga': 0.0,
                    'Durasi_Minggu': 1,
                    'Minggu_Mulai': 1
                }
                st.session_state['df_rab'] = pd.concat([st.session_state['df_rab'], pd.DataFrame([new_row])], ignore_index=True)
                calculate_system()
                st.rerun()

        st.divider()
        
        edited_rab = st.data_editor(
            st.session_state['df_rab'],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "No": st.column_config.NumberColumn(disabled=True),
                "Divisi": st.column_config.TextColumn(disabled=False, help="Kelompokkan pekerjaan di sini"),
                "Uraian_Pekerjaan": st.column_config.TextColumn(disabled=True, width="large"),
                "Kode_Analisa_Ref": st.column_config.TextColumn(disabled=True, help="Otomatis dari AHSP"),
                "Satuan_Pek": st.column_config.TextColumn("Satuan", width="small"),
                "Harga_Satuan_Jadi": st.column_config.NumberColumn("Harsat (+Ovhd)", format="Rp %d", disabled=True),
                "Total_Harga": st.column_config.NumberColumn("Total", format="Rp %d", disabled=True),
                "Volume": st.column_config.NumberColumn("Volume", disabled=False),
                "Durasi_Minggu": st.column_config.NumberColumn("Durasi (Mgg)", min_value=1, disabled=False),
                "Minggu_Mulai": st.column_config.NumberColumn("Start (Mgg)", min_value=1, disabled=False)
            }
        )
        
        if not edited_rab.equals(st.session_state['df_rab']):
            edited_rab['No'] = range(1, len(edited_rab) + 1)
            st.session_state['df_rab'] = edited_rab
            calculate_system()
            st.rerun()

        total_rab = st.session_state['df_rab']['Total_Harga'].sum()
        st.markdown(f"""
        <div style="background-color: #e6f3ff; padding: 15px; border-radius: 8px; text-align: right; border: 1px solid #2980b9; margin-top: 10px;">
            <h2 style="color: #2c3e50; margin:0;">TOTAL JUMLAH: Rp {total_rab:,.0f}</h2>
            <small>Termasuk Overhead {st.session_state['global_overhead']}%</small>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📂 Opsi Lanjutan (Import / Download)"):
            col_dl, col_up = st.columns([1, 2])
            with col_dl:
                template_rab_data = {
                    'Divisi': ['PEKERJAAN STRUKTUR BAWAH'],
                    'Uraian_Pekerjaan': ['Contoh: Pondasi Batu Kali'],
                    'Kode_Analisa_Ref': ['A.3.1'],
                    'Volume': [100]
                }
                st.download_button("📥 Download Template Excel", generate_excel_template(template_rab_data, "RAB"), "Template_Volume.xlsx")
            with col_up:
                uploaded_rab = st.file_uploader("Upload File Volume (Excel)", type=['xlsx'], key="upload_rab")
                if uploaded_rab: load_excel_rab_volume(uploaded_rab)
        
        st.download_button("📥 Download Excel RAB Lengkap", to_excel_download(st.session_state['df_rab'], "RAB"), "2_RAB_Detail.xlsx")
        render_footer()
    
    # === TAB 3: DETAIL ANALISA (SNI) ===
    with tabs[2]:
        st.header("Detail Analisa (AHSP)")
        render_print_button()
        col_sel, col_ov = st.columns([3, 1])
        with col_sel:
            df_det = st.session_state['df_analysis_detailed']
            unique_codes = df_det['Kode_Analisa'].unique()
            # Mapping kode ke uraian untuk display selectbox
            code_map = {}
            for c in unique_codes:
                rows = df_det[df_det['Kode_Analisa'] == c]
                if not rows.empty:
                    code_map[c] = f"{c} - {rows['Uraian_Pekerjaan'].iloc[0]}"
                else:
                    code_map[c] = f"{c} - Unknown"

            selected_code = st.selectbox("Pilih Pekerjaan:", unique_codes, format_func=lambda x: code_map.get(x, x))
        with col_ov:
            st.metric("Overhead Global", f"{st.session_state['global_overhead']}%")

        if selected_code:
            df_selected = df_det[df_det['Kode_Analisa'] == selected_code]
            if not df_selected.empty:
                desc_selected = df_selected['Uraian_Pekerjaan'].iloc[0]
                st.markdown(render_sni_html(selected_code, desc_selected, df_selected, st.session_state['global_overhead']), unsafe_allow_html=True)
        
        st.download_button("📥 Download Analisa", to_excel_download(df_det, "AHSP"), "3_Analisa.xlsx")
        
        # --- FEATURE UPDATE DATABASE (Sesuai Permintaan) ---
        with st.expander("📂 Update Database Analisa (Upload CSV SNI)"):
            st.info("Fitur ini memungkinkan Anda menambah analisa baru dari file CSV SNI tanpa mengubah kode.")
            up_analisa = st.file_uploader("Upload File CSV Analisa", type=['csv'])
            if up_analisa:
                parse_sni_csv_analysis(up_analisa)
        
        render_footer()

    # === TAB 4: HARGA SATUAN ===
    with tabs[3]:
        st.header("Master Harga Satuan")
        render_print_button()
        edited_prices = st.data_editor(st.session_state['df_prices'], num_rows="dynamic", use_container_width=True, 
                                       column_config={"Harga_Dasar": st.column_config.NumberColumn(format="Rp %d"), "Kategori": st.column_config.SelectboxColumn(options=['Upah', 'Material', 'Alat'], required=True)})
        if not edited_prices.equals(st.session_state['df_prices']):
            st.session_state['df_prices'] = edited_prices
            calculate_system()
            st.rerun()
        
        with st.expander("📂 Import Harga (Update Database)"):
             st.info("Mendukung Excel (.xlsx) atau CSV SNI (.csv)")
             uploaded_price = st.file_uploader("Upload File", type=['xlsx', 'csv'], key="upload_price")
             if uploaded_price: load_excel_prices(uploaded_price)

        st.download_button("📥 Download Harga", to_excel_download(st.session_state['df_prices'], "Harga"), "4_Harga.xlsx")
        render_footer()

    # === TAB 5: REKAP MATERIAL ===
    with tabs[4]:
        st.header("Rekap Material (Real Cost)")
        render_print_button()
        if 'df_material_rekap' in st.session_state:
            st.dataframe(st.session_state['df_material_rekap'], use_container_width=True, hide_index=True, 
                         column_config={"Total_Biaya_Material": st.column_config.NumberColumn(format="Rp %d"), "Total_Kebutuhan_Material": st.column_config.NumberColumn(format="%.2f")})
            
            total_mat = st.session_state['df_material_rekap']['Total_Biaya_Material'].sum()
            profit = total_mat * (st.session_state['global_overhead']/100)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Modal (Real Cost)", f"Rp {total_mat:,.0f}")
            col2.metric(f"Profit ({st.session_state['global_overhead']}%)", f"Rp {profit:,.0f}")
            col3.metric("Total Jual (RAB)", f"Rp {total_mat+profit:,.0f}")
            
            st.download_button("📥 Download Rekap", to_excel_download(st.session_state['df_material_rekap'], "Material"), "5_Rekap_Material.xlsx")
        render_footer()

    # === TAB 6: KURVA S ===
    with tabs[5]:
        st.header("📈 Kurva S - Jadwal Proyek")
        render_print_button()
        df_rab_curve, df_curve_data = generate_s_curve_data()
        
        if df_curve_data is not None:
            chart = alt.Chart(df_curve_data).mark_line(point=True, strokeWidth=3).encode(
                x=alt.X('Minggu_Int', title='Minggu Ke-', scale=alt.Scale(domainMin=1)),
                y=alt.Y('Rencana_Kumulatif', title='Bobot Kumulatif (%)', scale=alt.Scale(domain=[0, 100])),
                tooltip=['Minggu', 'Rencana_Kumulatif']
            ).interactive()
            st.altair_chart(chart, use_container_width=True)
            with st.expander("Lihat Data Mingguan"):
                 st.dataframe(df_curve_data.set_index('Minggu'), use_container_width=True)
        else:
            st.warning("Data RAB belum lengkap.")
        render_footer()

if __name__ == "__main__":
    main()


import streamlit as st
import pandas as pd
import io
import xlsxwriter
import altair as alt
import streamlit.components.v1 as components
from difflib import get_close_matches

# --- Konfigurasi Halaman ---
st.set_page_config(page_title="SmartRAB-SNI", layout="wide")

# --- 1. Inisialisasi Data (Database Lengkap) ---
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

    # === DATABASE HARGA SATUAN DASAR (RESOURCE) ===
    if 'df_prices' not in st.session_state:
        data_prices = {
            'Kode': [
                # UPAH
                'L.01', 'L.02', 'L.03', 'L.04', 'L.05', 'L.06',
                # MATERIAL - SIPIL & STRUKTUR
                'M.01', 'M.02', 'M.03', 'M.04', 'M.05', 'M.06', 'M.07', 'M.08', 'M.09', 'M.10',
                # MATERIAL - ARSITEKTUR
                'M.11', 'M.12', 'M.13', 'M.14', 'M.15', 'M.16', 'M.17', 'M.18', 'M.19',
                # MATERIAL - MEP (LISTRIK & SANITAIR)
                'M.20', 'M.21', 'M.22', 'M.23', 'M.24', 'M.25', 'M.26', 'M.27', 'M.28',
                # ALAT
                'E.01', 'E.02'
            ],
            'Komponen': [
                # UPAH
                'Pekerja', 'Tukang Batu', 'Tukang Kayu', 'Tukang Cat', 'Tukang Listrik', 'Kepala Tukang',
                # MATERIAL - SIPIL
                'Semen Portland', 'Pasir Beton', 'Pasir Pasang', 'Batu Kali', 'Split (Kerikil)', 
                'Batu Bata Merah', 'Bata Ringan (Hebel)', 'Semen Instan (Mortar)', 'Besi Beton Polos', 'Kawat Beton',
                # MATERIAL - ARS
                'Keramik 40x40', 'Granit 60x60', 'Semen Nat', 'Cat Tembok Interior', 'Cat Tembok Eksterior', 
                'Papan Gypsum 9mm', 'Rangka Hollow 40x40', 'Kusen Aluminium 4"', 'Kaca Polos 5mm',
                # MATERIAL - MEP
                'Pipa PVC 1/2"', 'Pipa PVC 3"', 'Kran Air 1/2"', 'Closet Duduk', 'Floor Drain',
                'Kabel NYM 3x2.5mm', 'Saklar Tunggal', 'Saklar Ganda', 'Stop Kontak',
                # ALAT
                'Sewa Molen', 'Stamper'
            ],
            'Satuan': [
                # UPAH
                'OH', 'OH', 'OH', 'OH', 'OH', 'OH',
                # SIPIL
                'kg', 'kg', 'm3', 'm3', 'kg', 
                'bh', 'bh', 'zak', 'kg', 'kg',
                # ARS
                'dos', 'dos', 'kg', 'kg', 'kg', 
                'lbr', 'btg', 'm1', 'm2',
                # MEP
                'btg', 'btg', 'bh', 'unit', 'bh',
                'm', 'bh', 'bh', 'bh',
                # ALAT
                'jam', 'jam'
            ],
            'Harga_Dasar': [
                # UPAH
                100000, 145000, 150000, 140000, 160000, 180000,
                # SIPIL
                1300, 300, 320000, 280000, 260000, 
                800, 8500, 65000, 14000, 25000,
                # ARS
                65000, 180000, 15000, 35000, 55000, 
                85000, 45000, 120000, 150000,
                # MEP
                45000, 120000, 35000, 2500000, 45000,
                15000, 35000, 45000, 40000,
                # ALAT
                85000, 150000
            ],
            'Kategori': [
                'Upah', 'Upah', 'Upah', 'Upah', 'Upah', 'Upah',
                'Material', 'Material', 'Material', 'Material', 'Material',
                'Material', 'Material', 'Material', 'Material', 'Material',
                'Material', 'Material', 'Material', 'Material', 'Material',
                'Material', 'Material', 'Material', 'Material',
                'Material', 'Material', 'Material', 'Material', 'Material',
                'Material', 'Material', 'Material', 'Material',
                'Alat', 'Alat'
            ]
        }
        st.session_state['df_prices'] = pd.DataFrame(data_prices)

    # === DATABASE ANALISA HARGA SATUAN (AHSP / RESEP) ===
    if 'df_analysis' not in st.session_state:
        data_analysis = {
            'Kode_Analisa': [],
            'Uraian_Pekerjaan': [],
            'Komponen': [],
            'Koefisien': []
        }
        
        # Helper function untuk mengisi data lebih rapi
        def add_analisa(kode, uraian, komponen_list):
            for komp, koef in komponen_list:
                data_analysis['Kode_Analisa'].append(kode)
                data_analysis['Uraian_Pekerjaan'].append(uraian)
                data_analysis['Komponen'].append(komp)
                data_analysis['Koefisien'].append(koef)

        # --- 1. PEKERJAAN PERSIAPAN & TANAH ---
        add_analisa('A.2.3.1', 'Galian Tanah Biasa sedalam 1 m', [('Pekerja', 0.75), ('Mandor', 0.025)])
        add_analisa('A.2.3.9', 'Urugan Pasir Bawah Pondasi', [('Pasir Pasang', 1.2), ('Pekerja', 0.3)])
        add_analisa('A.2.3.11', 'Urugan Tanah Kembali', [('Pekerja', 0.5)])

        # --- 2. PEKERJAAN PONDASI ---
        add_analisa('A.3.2.3', 'Pasangan Pondasi Batu Kali 1:4', [
            ('Batu Kali', 1.2), ('Semen Portland', 163.0), ('Pasir Pasang', 0.52), 
            ('Pekerja', 1.5), ('Tukang Batu', 0.75), ('Kepala Tukang', 0.075)
        ])
        
        # --- 3. PEKERJAAN BETON ---
        # Beton K-175 (Cor Lantai Kerja / Praktis)
        add_analisa('A.4.1.1.5', 'Membuat Beton Mutu fc 14.5 Mpa (K-175)', [
            ('Semen Portland', 326.0), ('Pasir Beton', 760.0), ('Split (Kerikil)', 1029.0),
            ('Pekerja', 1.65), ('Tukang Batu', 0.275), ('Sewa Molen', 0.25)
        ])
        # Beton K-250 (Struktural)
        add_analisa('A.4.1.1.7', 'Membuat Beton Mutu fc 21.7 Mpa (K-250)', [
            ('Semen Portland', 384.0), ('Pasir Beton', 692.0), ('Split (Kerikil)', 1039.0),
            ('Pekerja', 1.65), ('Tukang Batu', 0.275), ('Sewa Molen', 0.25)
        ])
        # Pembesian
        add_analisa('A.4.1.1.17', 'Pembesian 10kg dengan Besi Polos', [
            ('Besi Beton Polos', 10.5), ('Kawat Beton', 0.15), 
            ('Pekerja', 0.07), ('Tukang Batu', 0.07)
        ])

        # --- 4. PEKERJAAN DINDING ---
        add_analisa('A.4.4.1', 'Pasangan Dinding Bata Merah 1:4', [
            ('Batu Bata Merah', 70.0), ('Semen Portland', 11.5), ('Pasir Pasang', 0.043),
            ('Pekerja', 0.3), ('Tukang Batu', 0.1)
        ])
        add_analisa('A.4.4.3', 'Pasangan Dinding Hebel / Ringan', [
            ('Bata Ringan (Hebel)', 8.5), ('Semen Instan (Mortar)', 4.0),
            ('Pekerja', 0.2), ('Tukang Batu', 0.1)
        ])
        add_analisa('A.4.4.2', 'Plesteran 1:4 Tebal 15mm', [
            ('Semen Portland', 6.24), ('Pasir Pasang', 0.024),
            ('Pekerja', 0.3), ('Tukang Batu', 0.15)
        ])

        # --- 5. PEKERJAAN LANTAI & DINDING ---
        add_analisa('A.4.4.3.35', 'Pasang Lantai Keramik 40x40', [
            ('Keramik 40x40', 1.05), ('Semen Portland', 10.0), ('Pasir Pasang', 0.045), ('Semen Nat', 1.5),
            ('Pekerja', 0.7), ('Tukang Batu', 0.35)
        ])
        add_analisa('A.4.4.3.36', 'Pasang Lantai Granit 60x60', [
            ('Granit 60x60', 1.05), ('Semen Portland', 9.8), ('Pasir Pasang', 0.045), ('Semen Nat', 1.3),
            ('Pekerja', 0.7), ('Tukang Batu', 0.35)
        ])

        # --- 6. PEKERJAAN PLAFOND ---
        add_analisa('A.4.5.1', 'Rangka Plafond Hollow', [
            ('Rangka Hollow 40x40', 4.0), ('Pekerja', 0.25), ('Tukang Kayu', 0.25)
        ])
        add_analisa('A.4.5.2', 'Pasang Plafond Gypsum 9mm', [
            ('Papan Gypsum 9mm', 0.364), ('Pekerja', 0.1), ('Tukang Kayu', 0.05)
        ])

        # --- 7. PEKERJAAN PENGECATAN ---
        add_analisa('A.4.7.1', 'Pengecatan Tembok Baru (Interior)', [
            ('Cat Tembok Interior', 0.2), ('Pekerja', 0.02), ('Tukang Cat', 0.063)
        ])

        # --- 8. PEKERJAAN ELEKTRIKAL (ME) ---
        add_analisa('E.1.1', 'Instalasi Titik Lampu', [
            ('Kabel NYM 3x2.5mm', 5.0), ('Pipa PVC 1/2"', 1.0),
            ('Pekerja', 0.5), ('Tukang Listrik', 0.5)
        ])
        add_analisa('E.1.2', 'Pasang Stop Kontak', [
            ('Stop Kontak', 1.0), ('Pekerja', 0.1), ('Tukang Listrik', 0.2)
        ])
        add_analisa('E.1.3', 'Pasang Saklar Tunggal', [
            ('Saklar Tunggal', 1.0), ('Pekerja', 0.05), ('Tukang Listrik', 0.1)
        ])

        # --- 9. PEKERJAAN SANITAIR ---
        add_analisa('S.1.1', 'Pasang Closet Duduk', [
            ('Closet Duduk', 1.0), ('Pekerja', 1.5), ('Tukang Batu', 1.5)
        ])
        add_analisa('S.1.2', 'Pasang Floor Drain', [
            ('Floor Drain', 1.0), ('Pekerja', 0.1), ('Tukang Batu', 0.1)
        ])
        add_analisa('S.1.3', 'Pasang Kran Air 1/2"', [
            ('Kran Air 1/2"', 1.0), ('Pekerja', 0.05), ('Tukang Batu', 0.1)
        ])

        st.session_state['df_analysis'] = pd.DataFrame(data_analysis)

    if 'df_rab' not in st.session_state:
        data_rab = {
            'No': pd.Series(dtype='int'),
            'Divisi': pd.Series(dtype='str'),
            'Uraian_Pekerjaan': pd.Series(dtype='str'),
            'Kode_Analisa_Ref': pd.Series(dtype='str'),
            'Satuan_Pek': pd.Series(dtype='str'),
            'Volume': pd.Series(dtype='float'),
            'Harga_Satuan_Jadi': pd.Series(dtype='float'),
            'Total_Harga': pd.Series(dtype='float'),
            'Durasi_Minggu': pd.Series(dtype='int'),
            'Minggu_Mulai': pd.Series(dtype='int')
        }
        st.session_state['df_rab'] = pd.DataFrame(data_rab)
        
    calculate_system()
        
    calculate_system()

# --- 2. Mesin Logika Utama ---
def calculate_system():
    df_p = st.session_state['df_prices'].copy()
    df_a = st.session_state['df_analysis'].copy()
    df_r = st.session_state['df_rab'].copy()
    
    # 1. HITUNG AHSP
    overhead_pct = st.session_state.get('global_overhead', 15.0)
    overhead_factor = 1 + (overhead_pct / 100)

    df_p['Key'] = df_p['Komponen'].str.strip().str.lower()
    df_a['Key'] = df_a['Komponen'].str.strip().str.lower()

    merged_analysis = pd.merge(df_a, df_p[['Key', 'Harga_Dasar', 'Satuan', 'Kategori']], on='Key', how='left')
    merged_analysis['Harga_Dasar'] = merged_analysis['Harga_Dasar'].fillna(0)
    merged_analysis['Satuan'] = merged_analysis['Satuan'].fillna('-')
    merged_analysis['Kategori'] = merged_analysis['Kategori'].fillna('Material')
    merged_analysis['Subtotal'] = merged_analysis['Koefisien'] * merged_analysis['Harga_Dasar']
    
    st.session_state['df_analysis_detailed'] = merged_analysis 

    unit_prices_pure = merged_analysis.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices_pure['Harga_Kalkulasi'] = unit_prices_pure['Subtotal'] * overhead_factor 
    
    # 2. UPDATE RAB
    if not df_r.empty:
        # Pastikan kolom referensi string untuk merge
        df_r['Kode_Analisa_Ref'] = df_r['Kode_Analisa_Ref'].astype(str)
        unit_prices_pure['Kode_Analisa'] = unit_prices_pure['Kode_Analisa'].astype(str)

        df_r_temp = pd.merge(df_r, unit_prices_pure[['Kode_Analisa', 'Harga_Kalkulasi']], left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
        
        # FIX: Pastikan hasil perhitungan dikonversi ke FLOAT agar editor tidak crash
        df_r['Harga_Satuan_Jadi'] = pd.to_numeric(df_r_temp['Harga_Kalkulasi'], errors='coerce').fillna(0.0)
        df_r['Volume'] = pd.to_numeric(df_r['Volume'], errors='coerce').fillna(0.0)
        df_r['Total_Harga'] = df_r['Volume'] * df_r['Harga_Satuan_Jadi']
        
        st.session_state['df_rab'] = df_r

        # 3. REKAP MATERIAL
        material_breakdown = pd.merge(
            df_r[['Kode_Analisa_Ref', 'Volume']], 
            merged_analysis[['Kode_Analisa', 'Komponen', 'Satuan', 'Koefisien', 'Harga_Dasar']], 
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
    else:
        st.session_state['df_material_rekap'] = pd.DataFrame(columns=['Komponen', 'Satuan', 'Total_Kebutuhan_Material', 'Total_Biaya_Material'])

# --- 3. Parser & Smart Matcher ---

def find_best_match(uraian_input, database_uraian_list, database_df):
    if not isinstance(uraian_input, str): return "", 0
    matches = get_close_matches(uraian_input, database_uraian_list, n=1, cutoff=0.5)
    if matches:
        match_text = matches[0]
        row = database_df[database_df['Uraian_Pekerjaan'] == match_text].iloc[0]
        return row['Kode_Analisa'], match_text
    return "", ""

def load_excel_custom_template(uploaded_file):
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        header_row_idx = 0
        for i, row in df_raw.iterrows():
            row_str = row.astype(str).str.upper().tolist()
            if any("URAIAN" in x for x in row_str if x != 'nan'):
                header_row_idx = i
                break
        
        df = pd.read_excel(uploaded_file, header=header_row_idx)
        df.columns = df.columns.str.strip().str.upper()
        
        col_uraian = next((c for c in df.columns if 'URAIAN' in c), None)
        col_vol = next((c for c in df.columns if 'VOLUME' in c), None)
        col_sat = next((c for c in df.columns if 'SATUAN' in c), None)
        
        if not col_uraian or not col_vol:
            st.error("Gagal mendeteksi kolom URAIAN atau VOLUME. Pastikan format sesuai template.")
            return

        clean_data = []
        current_divisi = "UMUM"
        db_ahsp = st.session_state['df_analysis_detailed'][['Kode_Analisa', 'Uraian_Pekerjaan']].drop_duplicates()
        db_uraian_list = db_ahsp['Uraian_Pekerjaan'].tolist()

        for idx, row in df.iterrows():
            uraian = str(row[col_uraian]).strip()
            if uraian == 'nan' or uraian == '': continue
            
            vol = pd.to_numeric(row[col_vol], errors='coerce')
            sat = str(row[col_sat]).strip() if col_sat and str(row[col_sat]) != 'nan' else ''
            
            if pd.isna(vol) or vol == 0:
                current_divisi = uraian
                continue 
            
            detected_kode, matched_name = find_best_match(uraian, db_uraian_list, db_ahsp)
            
            clean_data.append({
                'No': len(clean_data) + 1,
                'Divisi': current_divisi,
                'Uraian_Pekerjaan': uraian,
                'Kode_Analisa_Ref': detected_kode, 
                'Satuan_Pek': sat,
                'Volume': vol,
                'Harga_Satuan_Jadi': 0.0,
                'Total_Harga': 0.0,
                'Durasi_Minggu': 1,
                'Minggu_Mulai': 1
            })
            
        if not clean_data:
            st.warning("Tidak ada item pekerjaan dengan Volume > 0.")
            return

        # FIX: Buat DataFrame Baru dan PAKSA tipe data numeric
        df_new = pd.DataFrame(clean_data)
        df_new['Volume'] = pd.to_numeric(df_new['Volume'], errors='coerce').fillna(0.0)
        df_new['Harga_Satuan_Jadi'] = pd.to_numeric(df_new['Harga_Satuan_Jadi'], errors='coerce').fillna(0.0)
        df_new['Total_Harga'] = pd.to_numeric(df_new['Total_Harga'], errors='coerce').fillna(0.0)
        df_new['Durasi_Minggu'] = pd.to_numeric(df_new['Durasi_Minggu'], errors='coerce').fillna(1).astype(int)
        df_new['Minggu_Mulai'] = pd.to_numeric(df_new['Minggu_Mulai'], errors='coerce').fillna(1).astype(int)
        
        st.session_state['df_rab'] = df_new
        calculate_system()
        match_count = sum(1 for x in clean_data if x['Kode_Analisa_Ref'] != "")
        st.success(f"Berhasil import {len(clean_data)} item. {match_count} item otomatis terdeteksi!")
        
    except Exception as e:
        st.error(f"Gagal membaca file: {e}")

# --- 4. Generate Template Excel User ---
def generate_user_style_template():
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet("Sheet1")
    
    fmt_header = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#D3D3D3', 'text_wrap': True})
    fmt_sub = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EFEFEF'})
    fmt_normal = workbook.add_format({'border': 1})
    fmt_input = workbook.add_format({'border': 1, 'bg_color': '#FFFFCC'}) 
    
    worksheet.merge_range('B2:B3', 'No', fmt_header)
    worksheet.merge_range('D2:D3', 'URAIAN PEKERJAAN', fmt_header)
    worksheet.write('E2', 'VOLUME', fmt_header)
    worksheet.write('F2', 'SATUAN', fmt_header)
    worksheet.write('E3', 'a', fmt_header)
    worksheet.write('F3', 'b', fmt_header)
    
    data_sample = [
        ('I', 'PEKERJAAN STRUKTUR BAWAH', None, None), 
        ('1', 'Pondasi Batu Kali 1:4', 50, 'm3'),      
        ('2', 'Beton Mutu fc 25 Mpa', 25, 'm3'),       
        ('II', 'PEKERJAAN STRUKTUR ATAS', None, None), 
        ('1', 'Beton Mutu fc 25 Mpa', 100, 'm3'),      
    ]
    
    row = 3
    for no, uraian, vol, sat in data_sample:
        if vol is None: 
            worksheet.write(row, 1, no, fmt_sub)
            worksheet.write(row, 3, uraian, fmt_sub)
            worksheet.write_blank(row, 4, '', fmt_sub) 
            worksheet.write_blank(row, 5, '', fmt_sub) 
        else: 
            worksheet.write(row, 1, '', fmt_normal) 
            worksheet.write(row, 2, no, fmt_normal) 
            worksheet.write(row, 3, uraian, fmt_normal)
            worksheet.write(row, 4, vol, fmt_input)
            worksheet.write(row, 5, sat, fmt_normal)
        row += 1
        
    worksheet.set_column('D:D', 40) 
    workbook.close()
    return output.getvalue()

# --- 5. Helper & UI Standard ---
def render_print_style():
    st.markdown("""<style>@media print {[data-testid="stHeader"],[data-testid="stSidebar"],[data-testid="stToolbar"],footer,.stDeployButton{display:none!important}.main .block-container{max-width:100%!important;padding:1rem!important}body{background-color:white!important;color:black!important}}</style>""", unsafe_allow_html=True)

def render_print_button():
    components.html("""<script>function cetak(){window.parent.print();}</script><div style="text-align:right;"><button onclick="cetak()" style="background-color:#f0f2f6;border:1px solid #ccc;padding:8px 16px;border-radius:4px;cursor:pointer;font-weight:bold;color:#333;">🖨️ Cetak Halaman</button></div>""", height=60)

def to_excel_download(df, sheet_name="Sheet1"):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name=sheet_name)
    writer.close()
    return output.getvalue()

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
    st.markdown("""<div style="text-align: right; color: red; font-size: 14px; font-weight: bold;">by SmartStudio, email smartstudioarsitek@gmail.com</div>""", unsafe_allow_html=True)

def render_sni_html(kode, uraian, df_part, overhead_pct):
    html = f"""<div style="font-family: Arial, sans-serif; font-size: 14px; color: black;"><div style="background-color: #d1d1d1; padding: 10px; border: 1px solid black; font-weight: bold;">ANALISA HARGA SATUAN (AHSP) <br>{kode} - {uraian}</div><table style="width:100%; border-collapse: collapse; border: 1px solid black;"><thead><tr style="background-color: #f0f0f0; text-align: center;"><th style="border: 1px solid black; padding: 5px;">No</th><th style="border: 1px solid black; padding: 5px;">Uraian</th><th style="border: 1px solid black; padding: 5px;">Sat</th><th style="border: 1px solid black; padding: 5px;">Koef</th><th style="border: 1px solid black; padding: 5px;">Harga</th><th style="border: 1px solid black; padding: 5px;">Jumlah</th></tr></thead><tbody>"""
    cat_map = {'Upah': 'TENAGA KERJA', 'Material': 'BAHAN', 'Alat': 'PERALATAN'}
    totals = {'Upah': 0, 'Material': 0, 'Alat': 0}
    for label, key in [('A', 'Upah'), ('B', 'Material'), ('C', 'Alat')]:
        html += f"""<tr style="background-color: #fafafa; font-weight: bold;"><td style="border: 1px solid black; text-align: center;">{label}</td><td colspan="5" style="border: 1px solid black;">{cat_map[key]}</td></tr>"""
        items = df_part[df_part['Kategori'] == key]
        for idx, row in enumerate(items.itertuples()):
            html += f"""<tr><td style="border: 1px solid black; text-align: center;">{idx+1}</td><td style="border: 1px solid black;">{row.Komponen}</td><td style="border: 1px solid black; text-align: center;">{row.Satuan}</td><td style="border: 1px solid black; text-align: center;">{row.Koefisien}</td><td style="border: 1px solid black; text-align: right;">{row.Harga_Dasar:,.0f}</td><td style="border: 1px solid black; text-align: right;">{row.Subtotal:,.0f}</td></tr>"""
            totals[key] += row.Subtotal
        html += f"""<tr><td colspan="5" style="border: 1px solid black; text-align: right; font-weight: bold;">JUMLAH {cat_map[key]}</td><td style="border: 1px solid black; text-align: right;">{totals[key]:,.0f}</td></tr>"""
    
    total = sum(totals.values())
    ov = total * (overhead_pct/100)
    html += f"""<tr style="background-color: #eee;"><td colspan="5" style="border: 1px solid black; text-align: right; font-weight: bold;">TOTAL (A+B+C)</td><td style="border: 1px solid black; text-align: right;">{total:,.0f}</td></tr><tr><td colspan="5" style="border: 1px solid black; text-align: right; font-weight: bold;">OVERHEAD {overhead_pct}%</td><td style="border: 1px solid black; text-align: right;">{ov:,.0f}</td></tr><tr style="background-color: #ccc; font-size: 16px;"><td colspan="5" style="border: 1px solid black; text-align: right; font-weight: bold;">HARGA SATUAN JADI</td><td style="border: 1px solid black; text-align: right; font-weight: bold;">{total+ov:,.0f}</td></tr></tbody></table></div>"""
    return html

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

def generate_s_curve_data():
    df = st.session_state['df_rab'].copy()
    if df.empty: return None, None
    grand_total = df['Total_Harga'].sum()
    if grand_total == 0: return None, None

    df['Bobot_Pct'] = (df['Total_Harga'] / grand_total) * 100
    df['Durasi_Minggu'] = df['Durasi_Minggu'].fillna(1).astype(int)
    df['Minggu_Mulai'] = df['Minggu_Mulai'].fillna(1).astype(int)

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
        cumulative_list.append({'Minggu': f"M{w}", 'Minggu_Int': w, 'Rencana_Kumulatif': cumulative_progress})
    return df, pd.DataFrame(cumulative_list)

# --- 6. Main UI ---
def main():
    initialize_data()
    render_print_style()
    
    st.title("🏗️ SmartRAB-SNI")
    st.caption("Sistem Integrated RAB & Material Control")
    
    tabs = st.tabs(["📊 1. REKAPITULASI", "📝 2. RAB PROYEK", "🔍 3. AHSP SNI", "💰 4. HARGA SATUAN", "🧱 5. REKAP MATERIAL", "📈 6. KURVA S"])

    # TAB 1: REKAP
    with tabs[0]:
        st.header("Rekapitulasi Biaya")
        render_print_button()
        col1, col2 = st.columns([2, 1])
        with col2:
            st.markdown("### ⚙️ Identitas Proyek")
            p_name = st.text_input("Nama Pekerjaan", st.session_state['project_name'])
            p_loc = st.text_input("Lokasi", st.session_state['project_loc'])
            p_year = st.text_input("Tahun", st.session_state['project_year'])
            if p_name != st.session_state['project_name'] or p_loc != st.session_state['project_loc']:
                st.session_state.update({'project_name': p_name, 'project_loc': p_loc, 'project_year': p_year})
                st.rerun()
            
            st.markdown("### ⚙️ Global Setting")
            new_ov = st.number_input("Overhead (%)", 0.0, 50.0, st.session_state['global_overhead'], 0.5)
            if new_ov != st.session_state['global_overhead']:
                st.session_state['global_overhead'] = new_ov
                calculate_system()
                st.rerun()
        
        with col1:
            render_project_identity()
            df_rekap = st.session_state['df_rab']
            if not df_rekap.empty:
                rekap_view = df_rekap.groupby('Divisi')['Total_Harga'].sum().reset_index()
                st.dataframe(rekap_view, use_container_width=True, hide_index=True, column_config={"Total_Harga": st.column_config.NumberColumn(format="Rp %d")})
                
                total = rekap_view['Total_Harga'].sum()
                ppn = total * 0.11
                st.markdown(f"""<div style='text-align:right'><h3>TOTAL: Rp {total+ppn:,.0f}</h3>(Termasuk PPN 11%)</div>""", unsafe_allow_html=True)
                st.download_button("📥 Download Excel Laporan", generate_rekap_final_excel(rekap_view, 11.0, st.session_state['project_name'], "WARTO SANTOSO", "LEADER"), "1_Rekap.xlsx")
            else:
                st.info("Belum ada data RAB. Silakan import di Tab 2.")
        render_footer()

    # TAB 2: RAB (CORE FEATURE)
    with tabs[1]:
        st.header("Rencana Anggaran Biaya")
        render_print_button()
        render_project_identity()
        
        st.markdown("### 📂 Import Data")
        col_dl, col_up = st.columns([1, 2])
        with col_dl:
            st.download_button("📥 Download Template Excel", generate_user_style_template(), "Template_RAB_Custom.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with col_up:
            uploaded_file = st.file_uploader("Upload Excel yang sudah diisi (Format Template)", type=['xlsx'])
            if uploaded_file: load_excel_custom_template(uploaded_file)

        # Editor RAB - FIXED DATA TYPES
        edited_rab = st.data_editor(
            st.session_state['df_rab'],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "No": st.column_config.NumberColumn(disabled=True),
                "Divisi": st.column_config.TextColumn(disabled=True),
                "Uraian_Pekerjaan": st.column_config.TextColumn(disabled=True),
                "Kode_Analisa_Ref": st.column_config.TextColumn(help="Auto-detected code"),
                "Harga_Satuan_Jadi": st.column_config.NumberColumn(disabled=True, format="Rp %d"),
                "Total_Harga": st.column_config.NumberColumn(disabled=True, format="Rp %d"),
                "Volume": st.column_config.NumberColumn(format="%.2f", disabled=False)
            }
        )
        
        if not edited_rab.equals(st.session_state['df_rab']):
            st.session_state['df_rab'] = edited_rab
            calculate_system()
            st.rerun()
            
        render_footer()

    # TAB 3: AHSP
    with tabs[2]:
        st.header("Detail Analisa")
        render_print_button()
        col_sel, col_ov = st.columns([3,1])
        with col_sel:
            unique = st.session_state['df_analysis_detailed']['Kode_Analisa'].unique()
            sel = st.selectbox("Pilih Analisa:", unique)
        
        df_part = st.session_state['df_analysis_detailed'][st.session_state['df_analysis_detailed']['Kode_Analisa'] == sel]
        desc = df_part['Uraian_Pekerjaan'].iloc[0]
        st.markdown(render_sni_html(sel, desc, df_part, st.session_state['global_overhead']), unsafe_allow_html=True)
        render_footer()

    # TAB 4: HARGA
    with tabs[3]:
        st.header("Master Harga Satuan")
        render_print_button()
        edited_p = st.data_editor(st.session_state['df_prices'], num_rows="dynamic", use_container_width=True, column_config={"Harga_Dasar": st.column_config.NumberColumn(format="Rp %d")})
        if not edited_p.equals(st.session_state['df_prices']):
            st.session_state['df_prices'] = edited_p
            calculate_system()
            st.rerun()
        render_footer()

    # TAB 5: MATERIAL
    with tabs[4]:
        st.header("Rekap Material")
        render_print_button()
        st.dataframe(st.session_state['df_material_rekap'], use_container_width=True, hide_index=True, column_config={"Total_Biaya_Material": st.column_config.NumberColumn(format="Rp %d")})
        render_footer()

    # TAB 6: KURVA S
    with tabs[5]:
        st.header("Kurva S")
        render_print_button()
        df_res, df_curve = generate_s_curve_data()
        if df_curve is not None:
            chart = alt.Chart(df_curve).mark_line(point=True).encode(x='Minggu_Int', y='Rencana_Kumulatif', tooltip=['Minggu', 'Rencana_Kumulatif']).interactive()
            st.altair_chart(chart, use_container_width=True)
        else:
            st.warning("Data belum lengkap.")
        render_footer()

if __name__ == "__main__":
    main()



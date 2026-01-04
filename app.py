import streamlit as st
import pandas as pd
import io
import xlsxwriter
import altair as alt
import streamlit.components.v1 as components
from difflib import get_close_matches

# --- Konfigurasi Halaman ---
st.set_page_config(page_title="SmartRAB-SNI", layout="wide")

# --- 1. Inisialisasi Data ---
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

    if 'df_prices' not in st.session_state:
        # Data Harga Dasar
        data_prices = {
            'Kode': ['M.01', 'M.02', 'M.03', 'L.01', 'L.02', 'L.03', 'L.04', 'L.05', 'E.01'],
            'Komponen': ['Semen Portland', 'Pasir Beton', 'Batu Kali', 'Pekerja', 'Tukang Batu', 'Kepala Tukang', 'Mandor', 'Tukang Las', 'Sewa Molen'],
            'Satuan': ['kg', 'kg', 'm3', 'OH', 'OH', 'OH', 'OH', 'OH', 'Jam'],
            'Harga_Dasar': [1300, 300, 286500, 100000, 145000, 175000, 200000, 145000, 85000],
            'Kategori': ['Material', 'Material', 'Material', 'Upah', 'Upah', 'Upah', 'Upah', 'Upah', 'Alat']
        }
        st.session_state['df_prices'] = pd.DataFrame(data_prices)

    if 'df_analysis' not in st.session_state:
        # Data Analisa (AHSP SNI) - Database Resep
        data_analysis = {
            'Kode_Analisa': ['A.2.2.1', 'A.2.2.1', 'A.2.2.1', 'A.2.2.1', 'A.2.2.1', 
                             'A.4.1.1', 'A.4.1.1', 'A.4.1.1', 'A.4.1.1', 'A.4.1.1'],
            'Uraian_Pekerjaan': ['Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4',
                                 'Beton Mutu fc 25 Mpa', 'Beton Mutu fc 25 Mpa', 'Beton Mutu fc 25 Mpa', 'Beton Mutu fc 25 Mpa', 'Beton Mutu fc 25 Mpa'],
            'Komponen': ['Batu Kali', 'Semen Portland', 'Pasir Beton', 'Pekerja', 'Tukang Batu',
                         'Semen Portland', 'Pasir Beton', 'Split (Asumsi)', 'Pekerja', 'Sewa Molen'],
            'Koefisien': [1.2, 163.0, 0.52, 1.5, 0.75,
                          350.0, 700.0, 1050.0, 2.0, 0.25]
        }
        st.session_state['df_analysis'] = pd.DataFrame(data_analysis)

    if 'df_rab' not in st.session_state:
        # Data RAB (Awal Kosong)
        data_rab = {
            'No': [], 'Divisi': [], 'Uraian_Pekerjaan': [], 'Kode_Analisa_Ref': [],
            'Satuan_Pek': [], 'Volume': [], 'Harga_Satuan_Jadi': [], 'Total_Harga': [],
            'Durasi_Minggu': [], 'Minggu_Mulai': []
        }
        st.session_state['df_rab'] = pd.DataFrame(data_rab)
        
    calculate_system()

# --- 2. Mesin Logika Utama ---
def calculate_system():
    df_p = st.session_state['df_prices'].copy()
    df_a = st.session_state['df_analysis'].copy()
    df_r = st.session_state['df_rab'].copy()
    
    overhead_pct = st.session_state.get('global_overhead', 15.0)
    overhead_factor = 1 + (overhead_pct / 100)

    df_p['Key'] = df_p['Komponen'].str.strip().str.lower()
    df_a['Key'] = df_a['Komponen'].str.strip().str.lower()

    # 1. Hitung Harga Satuan Dasar AHSP
    merged_analysis = pd.merge(df_a, df_p[['Key', 'Harga_Dasar', 'Satuan', 'Kategori']], on='Key', how='left')
    merged_analysis['Harga_Dasar'] = merged_analysis['Harga_Dasar'].fillna(0)
    merged_analysis['Satuan'] = merged_analysis['Satuan'].fillna('-')
    merged_analysis['Kategori'] = merged_analysis['Kategori'].fillna('Material')
    merged_analysis['Subtotal'] = merged_analysis['Koefisien'] * merged_analysis['Harga_Dasar']
    
    st.session_state['df_analysis_detailed'] = merged_analysis 

    unit_prices_pure = merged_analysis.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices_pure['Harga_Kalkulasi'] = unit_prices_pure['Subtotal'] * overhead_factor 
    
    # 2. Update RAB (Hanya jika RAB tidak kosong)
    if not df_r.empty:
        # Link RAB dengan Harga Satuan Jadi berdasarkan KODE
        df_r_temp = pd.merge(df_r, unit_prices_pure[['Kode_Analisa', 'Harga_Kalkulasi']], left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
        
        df_r['Harga_Satuan_Jadi'] = df_r_temp['Harga_Kalkulasi'].fillna(0)
        df_r['Total_Harga'] = df_r['Volume'] * df_r['Harga_Satuan_Jadi']
        
        st.session_state['df_rab'] = df_r

        # 3. Hitung Rekap Material
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
    """Mencari uraian pekerjaan yang paling mirip di database"""
    if not isinstance(uraian_input, str): return "", 0
    
    # Cari 1 match terbaik
    matches = get_close_matches(uraian_input, database_uraian_list, n=1, cutoff=0.5) # Cutoff 0.5 = 50% kemiripan
    
    if matches:
        match_text = matches[0]
        # Ambil Kode dari DB
        row = database_df[database_df['Uraian_Pekerjaan'] == match_text].iloc[0]
        return row['Kode_Analisa'], match_text
    return "", ""

def load_excel_custom_template(uploaded_file):
    """Parser KHUSUS untuk Template Kakak (No, Uraian, Vol, Satuan, a, b)"""
    try:
        # Baca Excel tanpa header dulu untuk inspeksi
        df_raw = pd.read_excel(uploaded_file, header=None)
        
        # Cari baris header (biasanya baris ke-2 atau ke-3 yang ada tulisan "URAIAN PEKERJAAN")
        header_row_idx = 0
        for i, row in df_raw.iterrows():
            row_str = row.astype(str).str.upper().tolist()
            if any("URAIAN" in x for x in row_str if x != 'nan'):
                header_row_idx = i
                break
        
        # Reload dengan header yang benar
        df = pd.read_excel(uploaded_file, header=header_row_idx)
        
        # Normalisasi nama kolom (karena kadang ada spasi 'URAIAN ', 'VOLUME ')
        df.columns = df.columns.str.strip().str.upper()
        
        # Mapping kolom dari Excel Kakak ke Sistem
        # Template Kakak: No (col 0/1), Uraian (col 2/3), Volume (col 4), Satuan (col 5)
        # Kita cari kolom kunci
        col_uraian = next((c for c in df.columns if 'URAIAN' in c), None)
        col_vol = next((c for c in df.columns if 'VOLUME' in c), None)
        col_sat = next((c for c in df.columns if 'SATUAN' in c), None)
        
        if not col_uraian or not col_vol:
            st.error("Gagal mendeteksi kolom URAIAN atau VOLUME. Pastikan format sesuai template.")
            return

        # Proses Data
        clean_data = []
        current_divisi = "UMUM"
        
        # Siapkan Database untuk Smart Match
        db_ahsp = st.session_state['df_analysis_detailed'][['Kode_Analisa', 'Uraian_Pekerjaan']].drop_duplicates()
        db_uraian_list = db_ahsp['Uraian_Pekerjaan'].tolist()

        for idx, row in df.iterrows():
            uraian = str(row[col_uraian]).strip()
            if uraian == 'nan' or uraian == '': continue
            
            vol = pd.to_numeric(row[col_vol], errors='coerce')
            sat = str(row[col_sat]).strip() if col_sat and str(row[col_sat]) != 'nan' else ''
            
            # Deteksi Header/Divisi (Jika Volume Kosong/NaN, anggap sebagai Judul Bab)
            if pd.isna(vol) or vol == 0:
                current_divisi = uraian
                continue # Skip baris ini, jangan masuk RAB, simpan sbg nama Divisi
            
            # Ini adalah Item Pekerjaan
            # Lakukan SMART MATCHING
            detected_kode, matched_name = find_best_match(uraian, db_uraian_list, db_ahsp)
            
            clean_data.append({
                'No': len(clean_data) + 1,
                'Divisi': current_divisi,
                'Uraian_Pekerjaan': uraian,
                'Kode_Analisa_Ref': detected_kode, # Hasil Auto-Detect
                'Satuan_Pek': sat,
                'Volume': vol,
                'Harga_Satuan_Jadi': 0,
                'Total_Harga': 0,
                'Durasi_Minggu': 1,
                'Minggu_Mulai': 1
            })
            
        if not clean_data:
            st.warning("Tidak ada item pekerjaan dengan Volume > 0 yang ditemukan.")
            return

        # Simpan ke State
        st.session_state['df_rab'] = pd.DataFrame(clean_data)
        calculate_system()
        
        # Laporan Hasil Import
        match_count = sum(1 for x in clean_data if x['Kode_Analisa_Ref'] != "")
        st.success(f"Berhasil import {len(clean_data)} item. {match_count} item otomatis terdeteksi harganya!")
        
    except Exception as e:
        st.error(f"Terjadi kesalahan saat membaca file: {e}")

# --- 4. Generate Template Excel User ---
def generate_user_style_template():
    """Membuat Template Excel persis seperti 'TEMPLETE VOLUME.xlsx'"""
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet("Sheet1")
    
    # Format
    fmt_header = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#D3D3D3', 'text_wrap': True})
    fmt_sub = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EFEFEF'})
    fmt_normal = workbook.add_format({'border': 1})
    fmt_input = workbook.add_format({'border': 1, 'bg_color': '#FFFFCC'}) # Kuning utk input
    
    # Header Row (Baris 2 di Excel user, index 1)
    # Kolom: A(kosong), B(No), C(kosong), D(URAIAN), E(VOLUME), F(SATUAN), G(a), H(b)
    worksheet.merge_range('B2:B3', 'No', fmt_header)
    worksheet.merge_range('D2:D3', 'URAIAN PEKERJAAN', fmt_header)
    worksheet.write('E2', 'VOLUME', fmt_header)
    worksheet.write('F2', 'SATUAN', fmt_header)
    worksheet.write('E3', 'a', fmt_header)
    worksheet.write('F3', 'b', fmt_header)
    
    # Contoh Data (Struktur User)
    data_sample = [
        ('I', 'PEKERJAAN STRUKTUR BAWAH', None, None), # Header
        ('1', 'Pondasi Batu Kali 1:4', 50, 'm3'),      # Item
        ('2', 'Beton Mutu fc 25 Mpa', 25, 'm3'),       # Item
        ('II', 'PEKERJAAN STRUKTUR ATAS', None, None), # Header
        ('1', 'Beton Mutu fc 25 Mpa', 100, 'm3'),      # Item
    ]
    
    row = 3
    for no, uraian, vol, sat in data_sample:
        if vol is None: # Header
            worksheet.write(row, 1, no, fmt_sub)
            worksheet.write(row, 3, uraian, fmt_sub)
            worksheet.write_blank(row, 4, '', fmt_sub) # Vol kosong
            worksheet.write_blank(row, 5, '', fmt_sub) # Sat kosong
        else: # Item
            worksheet.write(row, 1, '', fmt_normal) # Kolom No Induk kosong
            worksheet.write(row, 2, no, fmt_normal) # Sub no
            worksheet.write(row, 3, uraian, fmt_normal)
            worksheet.write(row, 4, vol, fmt_input)
            worksheet.write(row, 5, sat, fmt_normal)
        row += 1
        
    worksheet.set_column('D:D', 40) # Lebar kolom uraian
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
    # (Kode HTML SNI sama seperti sebelumnya, disingkat)
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

        # Editor RAB
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
                "Volume": st.column_config.NumberColumn(format="%.2f")
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

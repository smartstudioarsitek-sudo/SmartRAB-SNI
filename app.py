import streamlit as st
import pandas as pd
import io
import xlsxwriter
import altair as alt
import streamlit.components.v1 as components

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
        # Data Awal Kosong tapi terstruktur
        data_rab = {
            'No': [],
            'Divisi': [], 
            'Uraian_Pekerjaan': [],
            'Kode_Analisa_Ref': [],
            'Satuan_Pek': [],
            'Volume': [],
            'Harga_Satuan_Jadi': [],
            'Total_Harga': [],
            'Durasi_Minggu': [],
            'Minggu_Mulai': []
        }
        st.session_state['df_rab'] = pd.DataFrame(data_rab)
        
    calculate_system()

# --- 2. Mesin Logika Utama ---
def calculate_system():
    # Ambil data dari session state
    df_p = st.session_state['df_prices'].copy()
    df_a = st.session_state['df_analysis'].copy()
    df_r = st.session_state['df_rab'].copy()
    
    # 1. HITUNG AHSP (WAJIB JALAN MESKIPUN RAB KOSONG)
    # Ini memperbaiki Error KeyError: 'df_analysis_detailed'
    
    overhead_pct = st.session_state.get('global_overhead', 15.0)
    overhead_factor = 1 + (overhead_pct / 100)

    df_p['Key'] = df_p['Komponen'].str.strip().str.lower()
    df_a['Key'] = df_a['Komponen'].str.strip().str.lower()

    # Merge Analysis dengan Harga Dasar
    merged_analysis = pd.merge(df_a, df_p[['Key', 'Harga_Dasar', 'Satuan', 'Kategori']], on='Key', how='left')
    
    # Handle NaN
    merged_analysis['Harga_Dasar'] = merged_analysis['Harga_Dasar'].fillna(0)
    merged_analysis['Satuan'] = merged_analysis['Satuan'].fillna('-')
    merged_analysis['Kategori'] = merged_analysis['Kategori'].fillna('Material')
    
    # Hitung Subtotal per baris komponen
    merged_analysis['Subtotal'] = merged_analysis['Koefisien'] * merged_analysis['Harga_Dasar']
    
    # SIMPAN KE STATE (Agar Tab 3 tidak error)
    st.session_state['df_analysis_detailed'] = merged_analysis 

    # Hitung Harga Satuan Jadi per Item Pekerjaan
    unit_prices_pure = merged_analysis.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices_pure['Harga_Kalkulasi'] = unit_prices_pure['Subtotal'] * overhead_factor 
    
    # 2. UPDATE RAB (Hanya jika RAB ada isinya)
    if not df_r.empty:
        # Link RAB dengan Harga Satuan Jadi
        df_r_temp = pd.merge(df_r, unit_prices_pure[['Kode_Analisa', 'Harga_Kalkulasi']], left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
        
        df_r['Harga_Satuan_Jadi'] = df_r_temp['Harga_Kalkulasi'].fillna(0)
        df_r['Total_Harga'] = df_r['Volume'] * df_r['Harga_Satuan_Jadi']
        
        st.session_state['df_rab'] = df_r

        # 3. HITUNG REKAP MATERIAL
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
        # Jika RAB kosong, buat DataFrame kosong agar Tab 5 tidak error
        st.session_state['df_material_rekap'] = pd.DataFrame(columns=['Komponen', 'Satuan', 'Total_Kebutuhan_Material', 'Total_Biaya_Material'])

# --- 3. Logic Kurva S ---
def generate_s_curve_data():
    df = st.session_state['df_rab'].copy()
    if df.empty: return None, None
    
    grand_total = df['Total_Harga'].sum()
    if grand_total == 0: return None, None

    df['Bobot_Pct'] = (df['Total_Harga'] / grand_total) * 100
    
    # Handle NaN
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
        
        cumulative_list.append({
            'Minggu': f"M{w}",
            'Minggu_Int': w,
            'Rencana_Kumulatif': cumulative_progress
        })

    return df, pd.DataFrame(cumulative_list)

# --- 4. Helper UI Components & Excel Generators ---

def generate_full_template():
    """Membuat Template Excel yang strukturnya MIRIP PDF USER"""
    data = [
        ("I. PENERAPAN SMKK", "1", "Penyiapan RKK", "", "Ls"),
        ("I. PENERAPAN SMKK", "2", "Sosialisasi Promosi Pelatihan", "", "Ls"),
        ("I. PENERAPAN SMKK", "3", "Alat Pelindung Kerja (APK) & APD", "", "Ls"),
        ("II. PEKERJAAN PERSIAPAN", "1", "Pekerjaan Pembongkaran", "", "Ls"),
        ("II. PEKERJAAN PERSIAPAN", "2", "Persiapan Area Pembangunan", "", "Ls"),
        ("III. PEKERJAAN STRUKTUR BAWAH", "A.1", "Fondasi Bore Pile", "", "m'"),
        ("III. PEKERJAAN STRUKTUR BAWAH", "A.2", "Pekerjaan Pile Cap", "", "m3"),
        ("III. PEKERJAAN STRUKTUR BAWAH", "B.1", "Pekerjaan Pondasi Batu Kali", "A.2.2.1", "m3"), 
        ("III. PEKERJAAN STRUKTUR BAWAH", "B.2", "Pekerjaan Sloof 150x200", "A.4.1.1", "m3"),
        ("IV. PEKERJAAN STRUKTUR ATAS", "A.1", "Kolom Utama Lantai 1", "A.4.1.1", "m3"), 
        ("IV. PEKERJAAN STRUKTUR ATAS", "A.2", "Balok Utama Lantai 1", "A.4.1.1", "m3"), 
        ("IV. PEKERJAAN STRUKTUR ATAS", "A.4", "Plat Lantai 2", "A.4.1.1", "m3"), 
        ("V. PEKERJAAN ARSITEKTUR", "A.1", "Pasangan Dinding & Plesteran", "", "m2"),
        ("V. PEKERJAAN ARSITEKTUR", "B.1", "Pekerjaan Lantai", "", "m2"),
        ("V. PEKERJAAN ARSITEKTUR", "C.1", "Pekerjaan Plafond", "", "m2"),
        ("V. PEKERJAAN ARSITEKTUR", "D.1", "Pintu dan Jendela", "", "Unit"),
        ("VI. PEKERJAAN PLUMBING", "A", "Pekerjaan Sanitair", "", "Bh"),
        ("VI. PEKERJAAN PLUMBING", "B", "Instalasi Air Bersih", "", "m'"),
        ("VII. PEKERJAAN ELEKTRIKAL", "A", "Instalasi Kabel Feeder", "", "m'"),
        ("VII. PEKERJAAN ELEKTRIKAL", "B", "Instalasi Penerangan", "", "Titik"),
    ]
    
    df = pd.DataFrame(data, columns=["Divisi", "No", "Uraian_Pekerjaan", "Kode_Analisa_Ref", "Satuan_Pek"])
    df["Volume"] = 0.0 
    df["Durasi_Minggu"] = 1
    df["Minggu_Mulai"] = 1
    
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Template_RAB')
    
    workbook = writer.book
    worksheet = writer.sheets['Template_RAB']
    fmt_input = workbook.add_format({'bg_color': '#FFFF00', 'border': 1})
    worksheet.set_column('F:F', 15, fmt_input) # Kolom F adalah Volume
    writer.close()
    return output.getvalue()

def load_excel_rab_smart(uploaded_file):
    try:
        df_new = pd.read_excel(uploaded_file)
        required = ['Uraian_Pekerjaan', 'Volume']
        if not set(required).issubset(df_new.columns):
            st.error("Format Excel salah! Gunakan Template yang disediakan.")
            return

        df_clean = df_new[df_new['Volume'] > 0].copy()
        if df_clean.empty:
            st.warning("Tidak ada item pekerjaan dengan Volume > 0.")
            return

        df_clean['Harga_Satuan_Jadi'] = 0
        df_clean['Total_Harga'] = 0
        if 'Kode_Analisa_Ref' not in df_clean.columns: df_clean['Kode_Analisa_Ref'] = ""
        if 'Durasi_Minggu' not in df_clean.columns: df_clean['Durasi_Minggu'] = 1
        if 'Minggu_Mulai' not in df_clean.columns: df_clean['Minggu_Mulai'] = 1
        
        st.session_state['df_rab'] = df_clean
        calculate_system() 
        st.success(f"Berhasil mengimport {len(df_clean)} item pekerjaan!")
    except Exception as e:
        st.error(f"Gagal membaca file: {e}")

# ... (Render Functions: Print, PDF, Excel) ...
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

def load_excel_prices(uploaded_file):
    try:
        df_new = pd.read_excel(uploaded_file)
        st.session_state['df_prices'] = df_new
        calculate_system()
        st.success("Harga berhasil diupdate!")
    except: st.error("Gagal membaca file")

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
            new_overhead = st.number_input("Margin Profit / Overhead (%)", 0.0, 50.0, st.session_state['global_overhead'], 0.5)
            if new_overhead != st.session_state['global_overhead']:
                st.session_state['global_overhead'] = new_overhead
                calculate_system()
                st.rerun()

            ppn_input = st.number_input("PPN (%)", value=11.0, step=1.0)
            pt_input = st.text_input("Nama Perusahaan", value="SMARTSTUDIIO")
            signer_input = st.text_input("Penandatangan", value="WARTO SANTOSO, ST")
            pos_input = st.text_input("Jabatan", value="LEADER")
        
        df_rab = st.session_state['df_rab']
        if 'Divisi' in df_rab.columns and not df_rab.empty:
            rekap_divisi = df_rab.groupby('Divisi')['Total_Harga'].sum().reset_index()
        else:
            rekap_divisi = pd.DataFrame({'Divisi': ['-'], 'Total_Harga': [0]})
            
        total_biaya = rekap_divisi['Total_Harga'].sum()
        ppn_val = total_biaya * (ppn_input / 100)
        grand_total_val = total_biaya + ppn_val
        
        with col_main:
            render_project_identity()
            st.markdown("### Tabel Rekapitulasi")
            st.dataframe(rekap_divisi, use_container_width=True, hide_index=True, column_config={"Divisi": "URAIAN", "Total_Harga": st.column_config.NumberColumn(format="Rp %d")})
            
            st.markdown(f"""
            <div style="text-align: right; font-size: 16px; margin-top: 10px;">
                <b>TOTAL BIAYA : Rp {total_biaya:,.0f}</b><br>
                <b>PPN {ppn_input}% : Rp {ppn_val:,.0f}</b><br>
                <b style="font-size: 20px; color: blue;">TOTAL AKHIR : Rp {grand_total_val:,.0f}</b>
            </div>
            """, unsafe_allow_html=True)
        
        st.download_button("📥 Download Excel Laporan", generate_rekap_final_excel(rekap_divisi, ppn_input, pt_input, signer_input, pos_input), "1_Rekapitulasi_Biaya.xlsx")
        render_footer()

    # === TAB 2: RAB ===
    with tabs[1]:
        st.header("Rencana Anggaran Biaya")
        render_print_button()
        render_project_identity()

        edited_rab = st.data_editor(
            st.session_state['df_rab'],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "No": st.column_config.NumberColumn(disabled=True),
                "Divisi": st.column_config.TextColumn(disabled=True),
                "Uraian_Pekerjaan": st.column_config.TextColumn(disabled=True),
                "Kode_Analisa_Ref": st.column_config.TextColumn(disabled=True, help="Kode Link ke Database"),
                "Harga_Satuan_Jadi": st.column_config.NumberColumn(disabled=True, format="Rp %d"),
                "Total_Harga": st.column_config.NumberColumn(disabled=True, format="Rp %d"),
                "Volume": st.column_config.NumberColumn(disabled=False)
            }
        )
        if not edited_rab.equals(st.session_state['df_rab']):
            st.session_state['df_rab'] = edited_rab
            calculate_system()
            st.rerun()

        total_rab = st.session_state['df_rab']['Total_Harga'].sum()
        st.markdown(f"""<div style="background-color: #e6f3ff; padding: 10px; text-align: right;"><h3>TOTAL JUMLAH: Rp {total_rab:,.0f}</h3></div>""", unsafe_allow_html=True)

        with st.expander("📂 Import / Download Template RAB (LENGKAP)"):
            col_dl, col_up = st.columns([1, 2])
            with col_dl:
                st.download_button("📥 Download Template PDF", generate_full_template(), "Template_RAB_Sesuai_PDF.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            with col_up:
                uploaded_rab = st.file_uploader("Upload File Template yang Sudah Diisi", type=['xlsx'], key="upload_rab")
                if uploaded_rab: load_excel_rab_smart(uploaded_rab)
        
        st.download_button("📥 Download Excel RAB", to_excel_download(st.session_state['df_rab'], "RAB"), "2_RAB_Detail.xlsx")
        render_footer()

    # === TAB 3 (AHSP), 4 (Harga), 5 (Material), 6 (Kurva S) ===
    # (Kode untuk Tab 3, 4, 5, 6 SAMA PERSIS dengan sebelumnya)
    with tabs[2]:
        st.header("Detail Analisa (AHSP)")
        render_print_button()
        col_sel, col_ov = st.columns([3, 1])
        with col_sel:
            df_det = st.session_state['df_analysis_detailed']
            unique_codes = df_det['Kode_Analisa'].unique()
            code_map = {c: f"{c} - {df_det[df_det['Kode_Analisa'] == c]['Uraian_Pekerjaan'].iloc[0]}" for c in unique_codes}
            selected_code = st.selectbox("Pilih Pekerjaan:", unique_codes, format_func=lambda x: code_map[x])
        with col_ov: st.metric("Overhead Global", f"{st.session_state['global_overhead']}%")
        df_selected = df_det[df_det['Kode_Analisa'] == selected_code]
        desc_selected = df_selected['Uraian_Pekerjaan'].iloc[0]
        st.markdown(render_sni_html(selected_code, desc_selected, df_selected, st.session_state['global_overhead']), unsafe_allow_html=True)
        render_footer()

    with tabs[3]:
        st.header("Master Harga Satuan")
        render_print_button()
        edited_prices = st.data_editor(st.session_state['df_prices'], num_rows="dynamic", use_container_width=True, 
                                       column_config={"Harga_Dasar": st.column_config.NumberColumn(format="Rp %d")})
        if not edited_prices.equals(st.session_state['df_prices']):
            st.session_state['df_prices'] = edited_prices
            calculate_system()
            st.rerun()
        with st.expander("📂 Import Harga"):
             uploaded_price = st.file_uploader("Upload File", type=['xlsx'], key="upload_price")
             if uploaded_price: load_excel_prices(uploaded_price)
        render_footer()

    with tabs[4]:
        st.header("Rekap Material (Real Cost)")
        render_print_button()
        if 'df_material_rekap' in st.session_state:
            st.dataframe(st.session_state['df_material_rekap'], use_container_width=True, hide_index=True, 
                         column_config={"Total_Biaya_Material": st.column_config.NumberColumn(format="Rp %d"), "Total_Kebutuhan_Material": st.column_config.NumberColumn(format="%.2f")})
            total_mat = st.session_state['df_material_rekap']['Total_Biaya_Material'].sum()
            col1, col2, col3 = st.columns(3)
            col1.metric("Modal (Real Cost)", f"Rp {total_mat:,.0f}")
            col2.metric(f"Profit", f"Rp {total_mat * (st.session_state['global_overhead']/100):,.0f}")
            col3.metric("Total Jual", f"Rp {total_mat * (1 + st.session_state['global_overhead']/100):,.0f}")
        render_footer()

    with tabs[5]:
        st.header("📈 Kurva S")
        render_print_button()
        df_rab_curve, df_curve_data = generate_s_curve_data()
        if df_curve_data is not None:
            chart = alt.Chart(df_curve_data).mark_line(point=True).encode(x='Minggu_Int', y='Rencana_Kumulatif', tooltip=['Minggu', 'Rencana_Kumulatif']).interactive()
            st.altair_chart(chart, use_container_width=True)
            with st.expander("Lihat Data"): st.dataframe(df_curve_data.set_index('Minggu'), use_container_width=True)
        else: st.warning("Data RAB belum lengkap.")
        render_footer()

if __name__ == "__main__":
    main()

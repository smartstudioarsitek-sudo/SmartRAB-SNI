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
        data_prices = {
            'Kode': ['M.01', 'M.02', 'M.03', 'L.01', 'L.02', 'E.01'],
            'Komponen': ['Semen Portland', 'Pasir Beton', 'Batu Kali', 'Pekerja', 'Tukang Batu', 'Sewa Molen'],
            'Satuan': ['kg', 'kg', 'm3', 'OH', 'OH', 'Jam'],
            'Harga_Dasar': [1300, 300, 286500, 100000, 145000, 85000],
            'Kategori': ['Material', 'Material', 'Material', 'Upah', 'Upah', 'Alat']
        }
        st.session_state['df_prices'] = pd.DataFrame(data_prices)

    if 'df_analysis' not in st.session_state:
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
        data_rab = {
            'No': [1, 2],
            'Divisi': ['PEKERJAAN STRUKTUR BAWAH', 'PEKERJAAN STRUKTUR ATAS'], 
            'Uraian_Pekerjaan': ['Pondasi Batu Kali 1:4', 'Beton Mutu fc 25 Mpa'],
            'Kode_Analisa_Ref': ['A.2.2.1', 'A.4.1.1'],
            'Satuan_Pek': ['m3', 'm3'],
            'Volume': [50.0, 25.0],
            'Harga_Satuan_Jadi': [0.0, 0.0],
            'Total_Harga': [0.0, 0.0],
            'Durasi_Minggu': [2, 4],
            'Minggu_Mulai': [1, 3]
        }
        st.session_state['df_rab'] = pd.DataFrame(data_rab)
    
    if 'Durasi_Minggu' not in st.session_state['df_rab'].columns:
        st.session_state['df_rab']['Durasi_Minggu'] = 1
        st.session_state['df_rab']['Minggu_Mulai'] = 1
        
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

    # 1. Hitung Harga Satuan
    merged_analysis = pd.merge(df_a, df_p[['Key', 'Harga_Dasar', 'Satuan', 'Kategori']], on='Key', how='left')
    merged_analysis['Harga_Dasar'] = merged_analysis['Harga_Dasar'].fillna(0)
    merged_analysis['Satuan'] = merged_analysis['Satuan'].fillna('-')
    merged_analysis['Kategori'] = merged_analysis['Kategori'].fillna('Material')
    merged_analysis['Subtotal'] = merged_analysis['Koefisien'] * merged_analysis['Harga_Dasar']
    
    st.session_state['df_analysis_detailed'] = merged_analysis 

    unit_prices_pure = merged_analysis.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices_pure['Harga_Kalkulasi'] = unit_prices_pure['Subtotal'] * overhead_factor 
    
    # 2. Update RAB
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
    """Inject CSS khusus untuk mode cetak agar rapi"""
    st.markdown("""
        <style>
            @media print {
                /* Sembunyikan elemen bawaan Streamlit yang mengganggu saat print */
                [data-testid="stHeader"], 
                [data-testid="stSidebar"], 
                [data-testid="stToolbar"], 
                footer, 
                .stDeployButton {
                    display: none !important;
                }
                
                /* Atur konten utama agar full width dan bersih */
                .main .block-container {
                    max-width: 100% !important;
                    padding: 1rem !important;
                    box-shadow: none !important;
                }
                
                /* Paksa background putih dan text hitam */
                body {
                    background-color: white !important;
                    color: black !important;
                }
            }
        </style>
    """, unsafe_allow_html=True)

def render_print_button():
    """Tombol Print yang memanggil window.parent.print()"""
    components.html(
        """
        <script>
            function cetak() {
                window.parent.print();
            }
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

def load_excel_prices(uploaded_file):
    try:
        df_new = pd.read_excel(uploaded_file)
        required = ['Komponen', 'Harga_Dasar', 'Kategori'] 
        if not set(required).issubset(df_new.columns):
            st.error(f"Format Excel salah! Wajib ada kolom: {required}")
            return
        st.session_state['df_prices'] = df_new
        calculate_system()
        st.success("Harga berhasil diupdate!")
    except Exception as e:
        st.error(f"Gagal membaca file: {e}")

def load_excel_rab_volume(uploaded_file):
    try:
        df_new = pd.read_excel(uploaded_file)
        required = ['Divisi', 'Uraian_Pekerjaan', 'Kode_Analisa_Ref', 'Volume']
        if not set(required).issubset(df_new.columns):
            st.error(f"Format Excel salah! Wajib ada kolom: {required}")
            return
        
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
    render_print_style() # Inject CSS Print
    
    st.title("🏗️ SmartRAB-SNI") # <--- NAMA APLIKASI DIUBAH DISINI
    
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
        
        # TOMBOL PRINT
        render_print_button()
        
        col_main, col_set = st.columns([2, 1])
        
        with col_set:
            st.markdown("### ⚙️ Pengaturan & Identitas")
            
            # --- INPUT IDENTITAS PROYEK ---
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

        edited_rab = st.data_editor(
            st.session_state['df_rab'],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "No": st.column_config.NumberColumn(disabled=True),
                "Divisi": st.column_config.TextColumn(disabled=True, help="Ubah lewat Import Excel jika ingin ganti struktur"),
                "Uraian_Pekerjaan": st.column_config.TextColumn(disabled=True),
                "Kode_Analisa_Ref": st.column_config.TextColumn(disabled=True),
                "Harga_Satuan_Jadi": st.column_config.NumberColumn("Harga (+Ovhd)", format="Rp %d", disabled=True),
                "Total_Harga": st.column_config.NumberColumn("Total", format="Rp %d", disabled=True),
                "Volume": st.column_config.NumberColumn("Volume (Input)", disabled=False),
                "Durasi_Minggu": st.column_config.NumberColumn("Durasi (Mgg)", min_value=1, disabled=False),
                "Minggu_Mulai": st.column_config.NumberColumn("Start (Mgg)", min_value=1, disabled=False)
            }
        )
        if not edited_rab.equals(st.session_state['df_rab']):
            st.session_state['df_rab'] = edited_rab
            calculate_system()
            st.rerun()

        total_rab = st.session_state['df_rab']['Total_Harga'].sum()
        st.markdown(f"""
        <div style="background-color: #e6f3ff; padding: 15px; border-radius: 8px; text-align: right; border: 1px solid #2980b9;">
            <h2 style="color: #2c3e50; margin:0;">TOTAL JUMLAH: Rp {total_rab:,.0f}</h2>
            <small>Termasuk Overhead {st.session_state['global_overhead']}%</small>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📂 Import / Download Template Volume"):
            col_dl, col_up = st.columns([1, 2])
            with col_dl:
                template_rab_data = {
                    'Divisi': ['PEKERJAAN STRUKTUR BAWAH'],
                    'Uraian_Pekerjaan': ['Contoh: Pondasi Batu Kali'],
                    'Kode_Analisa_Ref': ['A.2.2.1'],
                    'Volume': [100]
                }
                st.download_button("📥 Download Template", generate_excel_template(template_rab_data, "RAB"), "Template_Volume.xlsx")
            with col_up:
                uploaded_rab = st.file_uploader("Upload File Volume", type=['xlsx'], key="upload_rab")
                if uploaded_rab: load_excel_rab_volume(uploaded_rab)
        
        st.download_button("📥 Download Excel RAB", to_excel_download(st.session_state['df_rab'], "RAB"), "2_RAB_Detail.xlsx")
        render_footer()

    # === TAB 3, 4, 5 (Standard) ===
    with tabs[2]:
        st.header("Detail Analisa (AHSP)")
        render_print_button()
        
        col_sel, col_ov = st.columns([3, 1])
        with col_sel:
            df_det = st.session_state['df_analysis_detailed']
            unique_codes = df_det['Kode_Analisa'].unique()
            code_map = {c: f"{c} - {df_det[df_det['Kode_Analisa'] == c]['Uraian_Pekerjaan'].iloc[0]}" for c in unique_codes}
            selected_code = st.selectbox("Pilih Pekerjaan:", unique_codes, format_func=lambda x: code_map[x])
        with col_ov:
            st.metric("Overhead Global", f"{st.session_state['global_overhead']}%")

        df_selected = df_det[df_det['Kode_Analisa'] == selected_code]
        desc_selected = df_selected['Uraian_Pekerjaan'].iloc[0]
        st.markdown(render_sni_html(selected_code, desc_selected, df_selected, st.session_state['global_overhead']), unsafe_allow_html=True)
        st.download_button("📥 Download Analisa", to_excel_download(df_det, "AHSP"), "3_Analisa.xlsx")
        render_footer()

    with tabs[3]:
        st.header("Master Harga Satuan")
        render_print_button()
        
        edited_prices = st.data_editor(st.session_state['df_prices'], num_rows="dynamic", use_container_width=True, 
                                       column_config={"Harga_Dasar": st.column_config.NumberColumn(format="Rp %d"), "Kategori": st.column_config.SelectboxColumn(options=['Upah', 'Material', 'Alat'], required=True)})
        if not edited_prices.equals(st.session_state['df_prices']):
            st.session_state['df_prices'] = edited_prices
            calculate_system()
            st.rerun()
        
        with st.expander("📂 Import Harga"):
             uploaded_price = st.file_uploader("Upload File", type=['xlsx'], key="upload_price")
             if uploaded_price: load_excel_prices(uploaded_price)

        st.download_button("📥 Download Harga", to_excel_download(st.session_state['df_prices'], "Harga"), "4_Harga.xlsx")
        render_footer()

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

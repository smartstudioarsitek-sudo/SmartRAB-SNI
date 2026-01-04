import streamlit as st
import pandas as pd
import io
import xlsxwriter

# --- Konfigurasi Halaman ---
st.set_page_config(page_title="Sistem RAB Pro SNI", layout="wide")

# --- 1. Inisialisasi Data (Dummy Data) ---
def initialize_data():
    if 'df_prices' not in st.session_state:
        # Data Harga Dasar
        data_prices = {
            'Kode': ['M.01', 'M.02', 'M.03', 'L.01', 'L.02', 'E.01'],
            'Komponen': ['Semen Portland', 'Pasir Beton', 'Batu Kali', 'Pekerja', 'Tukang Batu', 'Sewa Molen'],
            'Satuan': ['kg', 'kg', 'm3', 'OH', 'OH', 'Jam'],
            'Harga_Dasar': [1300, 300, 286500, 100000, 145000, 85000],
            'Kategori': ['Material', 'Material', 'Material', 'Upah', 'Upah', 'Alat']
        }
        st.session_state['df_prices'] = pd.DataFrame(data_prices)

    if 'df_analysis' not in st.session_state:
        # Data Analisa (AHSP SNI)
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
        # Data RAB (Volume Project)
        data_rab = {
            'No': [1, 2],
            'Divisi': ['PEKERJAAN STRUKTUR BAWAH', 'PEKERJAAN STRUKTUR ATAS'], 
            'Uraian_Pekerjaan': ['Pondasi Batu Kali 1:4', 'Beton Mutu fc 25 Mpa'],
            'Kode_Analisa_Ref': ['A.2.2.1', 'A.4.1.1'],
            'Satuan_Pek': ['m3', 'm3'],
            'Volume': [50.0, 25.0],
            'Harga_Satuan_Jadi': [0.0, 0.0],
            'Total_Harga': [0.0, 0.0]
        }
        st.session_state['df_rab'] = pd.DataFrame(data_rab)
        
    calculate_system()

# --- 2. Mesin Logika Utama ---
def calculate_system():
    df_p = st.session_state['df_prices'].copy()
    df_a = st.session_state['df_analysis'].copy()
    df_r = st.session_state['df_rab'].copy()

    # Normalisasi Key
    df_p['Key'] = df_p['Komponen'].str.strip().str.lower()
    df_a['Key'] = df_a['Komponen'].str.strip().str.lower()

    # 1. Hitung Harga Satuan per Analisa
    merged_analysis = pd.merge(df_a, df_p[['Key', 'Harga_Dasar', 'Satuan', 'Kategori']], on='Key', how='left')
    
    merged_analysis['Harga_Dasar'] = merged_analysis['Harga_Dasar'].fillna(0)
    merged_analysis['Satuan'] = merged_analysis['Satuan'].fillna('-')
    merged_analysis['Kategori'] = merged_analysis['Kategori'].fillna('Material')
    
    merged_analysis['Subtotal'] = merged_analysis['Koefisien'] * merged_analysis['Harga_Dasar']
    
    st.session_state['df_analysis_detailed'] = merged_analysis 

    # Agregat Harga Satuan Jadi (Total Murni sebelum Overhead user input)
    overhead_default = 1.15 
    
    unit_prices_pure = merged_analysis.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices_pure['Harga_Kalkulasi'] = unit_prices_pure['Subtotal'] * overhead_default 
    
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

# --- 3. Fungsi Helper Excel & Format ---

def render_footer():
    """Menampilkan footer di setiap tab"""
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: grey; font-size: 12px;">
        by SmartStudio, email smartstudioarsitek@gmail.com
    </div>
    """, unsafe_allow_html=True)

def generate_excel_template(data_dict, sheet_name):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df = pd.DataFrame(data_dict)
    df.to_excel(writer, index=False, sheet_name=sheet_name)
    writer.close()
    return output.getvalue()

def to_excel_download(df, sheet_name="Sheet1"):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name=sheet_name)
    writer.close()
    return output.getvalue()

def generate_rekap_final_excel(df_rekap, ppn_pct, pt_name, signer, position):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    workbook = writer.book
    worksheet = workbook.add_worksheet('Rekapitulasi')

    # Format
    fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D3D3D3'})
    fmt_currency = workbook.add_format({'num_format': '#,##0', 'border': 1})
    fmt_text = workbook.add_format({'border': 1})
    fmt_bold = workbook.add_format({'bold': True, 'border': 1})
    
    # Judul
    worksheet.merge_range('A1:C1', 'REKAPITULASI BIAYA', workbook.add_format({'bold': True, 'align': 'center', 'font_size': 14}))
    worksheet.merge_range('A2:C2', 'ENGINEERING ESTIMATE', workbook.add_format({'bold': True, 'align': 'center'}))
    
    # Table Header
    worksheet.write(4, 0, 'No', fmt_header)
    worksheet.write(4, 1, 'URAIAN PEKERJAAN', fmt_header)
    worksheet.write(4, 2, 'TOTAL (Rp)', fmt_header)
    
    # Isi Data
    row = 5
    total_biaya = 0
    for idx, r in df_rekap.iterrows():
        worksheet.write(row, 0, chr(65+idx), fmt_text) # A, B, C...
        worksheet.write(row, 1, r['Divisi'], fmt_text)
        worksheet.write(row, 2, r['Total_Harga'], fmt_currency)
        total_biaya += r['Total_Harga']
        row += 1
        
    # Footer (Subtotal, PPN, Total)
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
    
    # Tanda Tangan
    row += 3
    worksheet.write(row, 2, pt_name, workbook.add_format({'bold': True, 'align': 'center'}))
    row += 4
    worksheet.write(row, 2, signer, workbook.add_format({'bold': True, 'align': 'center', 'underline': True}))
    row += 1
    worksheet.write(row, 2, position, workbook.add_format({'align': 'center'}))

    # Lebar Kolom
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
        # Menambahkan 'Divisi' sebagai kolom wajib untuk fitur rekap baru
        required = ['Divisi', 'Uraian_Pekerjaan', 'Kode_Analisa_Ref', 'Volume']
        if not set(required).issubset(df_new.columns):
            st.error(f"Format Excel salah! Wajib ada kolom: {required}")
            return
        
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

# Fungsi Render HTML Tabel SNI
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

# --- 4. Main UI ---
def main():
    initialize_data()
    
    st.title("🏗️ Sistem Integrated RAB & Material Control")
    
    tabs = st.tabs([
        "📊 1. REKAPITULASI", 
        "📝 2. RAB PROYEK", 
        "🔍 3. AHSP SNI", 
        "💰 4. HARGA SATUAN", 
        "🧱 5. REKAP MATERIAL"
    ])

    # === TAB 1: REKAPITULASI ===
    with tabs[0]:
        st.header("Rekapitulasi Biaya (Engineering Estimate)")
        
        col_main, col_set = st.columns([2, 1])
        
        with col_set:
            st.markdown("### Pengaturan Laporan")
            # DEFAULT VALUES SESUAI PERMINTAAN
            ppn_input = st.number_input("PPN (%)", value=11.0, step=1.0)
            pt_input = st.text_input("Nama Perusahaan (Kop)", value="SMARTSTUDIO")
            signer_input = st.text_input("Nama Penandatangan", value="WARTO SANTOSO, ST")
            pos_input = st.text_input("Jabatan", value="LEADER")
        
        # Kelompokkan RAB berdasarkan 'Divisi'
        df_rab = st.session_state['df_rab']
        if 'Divisi' in df_rab.columns:
            rekap_divisi = df_rab.groupby('Divisi')['Total_Harga'].sum().reset_index()
        else:
            rekap_divisi = pd.DataFrame({'Divisi': ['Umum'], 'Total_Harga': [df_rab['Total_Harga'].sum()]})
            
        total_biaya = rekap_divisi['Total_Harga'].sum()
        ppn_val = total_biaya * (ppn_input / 100)
        grand_total_val = total_biaya + ppn_val
        
        with col_main:
            # Tampilkan Tabel Rekap
            st.markdown("### Tabel Rekapitulasi")
            
            rekap_display = rekap_divisi.copy()
            rekap_display.columns = ['URAIAN PEKERJAAN', 'TOTAL (Rp)']
            st.dataframe(rekap_display, use_container_width=True, hide_index=True, 
                         column_config={"TOTAL (Rp)": st.column_config.NumberColumn(format="Rp %d")})
            
            # Tampilkan Total Bawah
            st.markdown(f"""
            <div style="text-align: right; font-size: 16px; margin-top: 10px;">
                <b>TOTAL BIAYA : Rp {total_biaya:,.0f}</b><br>
                <b>PPN {ppn_input}% : Rp {ppn_val:,.0f}</b><br>
                <b style="font-size: 20px; color: blue;">TOTAL AKHIR : Rp {grand_total_val:,.0f}</b>
            </div>
            """, unsafe_allow_html=True)
        
        # Download Button Spesifik Tab 1
        excel_rekap = generate_rekap_final_excel(rekap_divisi, ppn_input, pt_input, signer_input, pos_input)
        st.download_button(
            label="📥 Download Excel Rekapitulasi (Format Laporan)",
            data=excel_rekap,
            file_name="1_Rekapitulasi_Biaya.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # FOOTER
        render_footer()

    # === TAB 2: RAB ===
    with tabs[1]:
        st.header("Rencana Anggaran Biaya")
        with st.expander("📂 Import / Download Template Volume"):
            col_dl, col_up = st.columns([1, 2])
            with col_dl:
                st.write("**1. Download Template**")
                template_rab_data = {
                    'Divisi': ['PEKERJAAN STRUKTUR BAWAH'],
                    'Uraian_Pekerjaan': ['Contoh: Pondasi Batu Kali'],
                    'Kode_Analisa_Ref': ['A.2.2.1'],
                    'Volume': [100]
                }
                excel_rab_template = generate_excel_template(template_rab_data, "Template_RAB")
                st.download_button(
                    label="📥 Download Template Excel",
                    data=excel_rab_template,
                    file_name="Template_Import_Volume.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            with col_up:
                st.write("**2. Upload File Anda**")
                uploaded_rab = st.file_uploader("Upload File Volume", type=['xlsx'], key="upload_rab")
                if uploaded_rab:
                    load_excel_rab_volume(uploaded_rab)

        edited_rab = st.data_editor(
            st.session_state['df_rab'],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "No": st.column_config.NumberColumn(disabled=True),
                "Divisi": st.column_config.TextColumn(disabled=False, help="Kategori Pekerjaan (misal: Struktur)"),
                "Uraian_Pekerjaan": st.column_config.TextColumn(disabled=True),
                "Kode_Analisa_Ref": st.column_config.TextColumn(disabled=True),
                "Harga_Satuan_Jadi": st.column_config.NumberColumn("Harga Satuan (+Overhead)", format="Rp %d", disabled=True),
                "Total_Harga": st.column_config.NumberColumn("Total", format="Rp %d", disabled=True),
                "Volume": st.column_config.NumberColumn("Volume (Input)")
            }
        )
        if not edited_rab.equals(st.session_state['df_rab']):
            st.session_state['df_rab'] = edited_rab
            calculate_system()
            st.rerun()

        # TOTAL JUMLAH BESAR DI BAWAH
        total_rab = st.session_state['df_rab']['Total_Harga'].sum()
        st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: right; margin-top: 20px;">
            <h2 style="color: #31333F; margin:0;">TOTAL JUMLAH: Rp {total_rab:,.0f}</h2>
        </div>
        """, unsafe_allow_html=True)
        
        # Download Button Tab 2
        st.download_button(
            label="📥 Download Excel RAB Detail",
            data=to_excel_download(st.session_state['df_rab'], "RAB_Detail"),
            file_name="2_RAB_Detail.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # FOOTER
        render_footer()

    # === TAB 3: AHSP SNI ===
    with tabs[2]:
        st.header("Detail Analisa Harga Satuan (Format SNI)")
        
        col_sel, col_ov = st.columns([3, 1])
        with col_sel:
            df_det = st.session_state['df_analysis_detailed']
            unique_codes = df_det['Kode_Analisa'].unique()
            code_map = {}
            for c in unique_codes:
                desc = df_det[df_det['Kode_Analisa'] == c]['Uraian_Pekerjaan'].iloc[0]
                code_map[c] = f"{c} - {desc}"
            
            selected_code = st.selectbox("Pilih Item Pekerjaan:", unique_codes, format_func=lambda x: code_map[x])
        
        with col_ov:
            overhead_pct = st.number_input("Overhead (%)", min_value=0.0, max_value=50.0, value=15.0, step=0.5)

        df_selected = df_det[df_det['Kode_Analisa'] == selected_code]
        desc_selected = df_selected['Uraian_Pekerjaan'].iloc[0]
        
        html_table = render_sni_html(selected_code, desc_selected, df_selected, overhead_pct)
        st.markdown(html_table, unsafe_allow_html=True)
        st.caption("*Format standar AHSP Bina Marga/Cipta Karya.")

        # Download Button Tab 3 (Download Raw Data Analisa)
        st.download_button(
            label="📥 Download Data Analisa (Raw Data)",
            data=to_excel_download(df_det, "AHSP_Data"),
            file_name="3_Data_Analisa_AHSP.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # FOOTER
        render_footer()

    # === TAB 4: HARGA SATUAN ===
    with tabs[3]:
        st.header("Master Harga Satuan Dasar")
        with st.expander("📂 Import / Download Template Harga"):
            col_dl_p, col_up_p = st.columns([1, 2])
            with col_dl_p:
                st.write("**1. Download Template**")
                template_price_data = {
                    'Komponen': ['Semen Portland', 'Pekerja'],
                    'Harga_Dasar': [1300, 100000],
                    'Satuan': ['kg', 'OH'],
                    'Kategori': ['Material', 'Upah']
                }
                excel_price_template = generate_excel_template(template_price_data, "Template_Harga")
                st.download_button(
                    label="📥 Download Template Excel",
                    data=excel_price_template,
                    file_name="Template_Import_Harga.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            with col_up_p:
                uploaded_price = st.file_uploader("Upload File Harga", type=['xlsx'], key="upload_price")
                if uploaded_price:
                    load_excel_prices(uploaded_price)

        edited_prices = st.data_editor(
            st.session_state['df_prices'],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Harga_Dasar": st.column_config.NumberColumn("Harga Dasar (Input)", format="Rp %d"),
                "Kategori": st.column_config.SelectboxColumn("Kategori (SNI)", options=['Upah', 'Material', 'Alat'], required=True)
            }
        )
        if not edited_prices.equals(st.session_state['df_prices']):
            st.session_state['df_prices'] = edited_prices
            calculate_system()
            st.rerun()
        
        # Download Button Tab 4
        st.download_button(
            label="📥 Download Excel Harga Satuan",
            data=to_excel_download(st.session_state['df_prices'], "Harga_Satuan"),
            file_name="4_Master_Harga_Satuan.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # FOOTER
        render_footer()

    # === TAB 5: REKAP MATERIAL ===
    with tabs[4]:
        st.header("Rekapitulasi Kebutuhan Material")
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
            
            # Download Button Tab 5
            st.download_button(
                label="📥 Download Rekap Material",
                data=to_excel_download(st.session_state['df_material_rekap'], "Rekap_Material"),
                file_name="5_Rekap_Kebutuhan_Material.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Data belum tersedia.")
            
        # FOOTER
        render_footer()

if __name__ == "__main__":
    main()

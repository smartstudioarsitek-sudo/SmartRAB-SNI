import streamlit as st
import pandas as pd
import io
import xlsxwriter
import altair as alt
import streamlit.components.v1 as components

# --- Konfigurasi Halaman ---
st.set_page_config(page_title="SmartRAB-SNI", layout="wide", page_icon="🏗️")

# --- 1. Inisialisasi Data ---
def initialize_data():
    defaults = {
        'global_overhead': 15.0,
        'project_name': 'Proyek Perumahan',
        'project_loc': 'Jakarta',
        'project_year': '2025'
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    if 'df_prices' not in st.session_state:
        # Data Dummy Minimal
        data_prices = {
            'Kode': ['M.01', 'L.01'],
            'Komponen': ['Semen Portland', 'Pekerja'],
            'Satuan': ['kg', 'OH'],
            'Harga_Dasar': [1300, 100000],
            'Kategori': ['Material', 'Upah']
        }
        st.session_state['df_prices'] = pd.DataFrame(data_prices)

    if 'df_analysis' not in st.session_state:
        st.session_state['df_analysis'] = pd.DataFrame(columns=['Kode_Analisa', 'Uraian_Pekerjaan', 'Komponen', 'Koefisien'])

    if 'df_rab' not in st.session_state:
        st.session_state['df_rab'] = pd.DataFrame(columns=[
            'No', 'Divisi', 'Uraian_Pekerjaan', 'Kode_Analisa_Ref', 
            'Satuan_Pek', 'Volume', 'Harga_Satuan_Jadi', 'Total_Harga', 
            'Durasi_Minggu', 'Minggu_Mulai'
        ])

    calculate_system()

# --- 2. Mesin Logika Utama ---
def calculate_system():
    df_p = st.session_state['df_prices'].copy()
    df_a = st.session_state['df_analysis'].copy()
    df_r = st.session_state['df_rab'].copy()
    
    overhead_pct = st.session_state.get('global_overhead', 15.0)
    overhead_factor = 1 + (overhead_pct / 100)

    # Normalisasi Key
    if not df_p.empty: df_p['Key'] = df_p['Komponen'].astype(str).str.strip().str.lower()
    if not df_a.empty: df_a['Key'] = df_a['Komponen'].astype(str).str.strip().str.lower()

    # 1. Hitung Harga Satuan
    if not df_a.empty and not df_p.empty:
        merged_analysis = pd.merge(df_a, df_p[['Key', 'Harga_Dasar', 'Satuan', 'Kategori']], on='Key', how='left')
        merged_analysis['Harga_Dasar'] = merged_analysis['Harga_Dasar'].fillna(0)
        merged_analysis['Subtotal'] = merged_analysis['Koefisien'] * merged_analysis['Harga_Dasar']
        st.session_state['df_analysis_detailed'] = merged_analysis 
        
        unit_prices_pure = merged_analysis.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
        unit_prices_pure['Harga_Kalkulasi'] = unit_prices_pure['Subtotal'] * overhead_factor
    else:
        st.session_state['df_analysis_detailed'] = pd.DataFrame()
        unit_prices_pure = pd.DataFrame(columns=['Kode_Analisa', 'Harga_Kalkulasi'])

    # 2. Update RAB
    if not df_r.empty:
        df_r['Kode_Analisa_Ref'] = df_r['Kode_Analisa_Ref'].astype(str).str.strip()
        unit_prices_pure['Kode_Analisa'] = unit_prices_pure['Kode_Analisa'].astype(str).str.strip()
        
        df_r_temp = pd.merge(df_r, unit_prices_pure[['Kode_Analisa', 'Harga_Kalkulasi']], left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
        df_r['Harga_Satuan_Jadi'] = df_r_temp['Harga_Kalkulasi'].fillna(0)
        df_r['Total_Harga'] = df_r['Volume'] * df_r['Harga_Satuan_Jadi']
        st.session_state['df_rab'] = df_r
        
        # 3. Rekap Material
        if not st.session_state['df_analysis_detailed'].empty:
            material_breakdown = pd.merge(
                df_r[['Kode_Analisa_Ref', 'Volume']], 
                st.session_state['df_analysis_detailed'][['Kode_Analisa', 'Komponen', 'Satuan', 'Koefisien', 'Harga_Dasar']], 
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
        st.session_state['df_material_rekap'] = pd.DataFrame()

# --- 3. Fungsi Load Pintar (Excel & CSV) ---
def smart_load_file(uploaded_file):
    try:
        filename = uploaded_file.name
        df_raw = None
        
        # 1. Baca File Mentah (Skip error lines)
        if filename.endswith('.csv'):
            try:
                df_raw = pd.read_csv(uploaded_file, header=None, on_bad_lines='skip')
            except:
                df_raw = pd.read_csv(uploaded_file, header=None, sep=';', on_bad_lines='skip') # Coba separator titik koma
        else:
            df_raw = pd.read_excel(uploaded_file, header=None)
            
        # 2. Cari Lokasi Header (Baris yg mengandung kata 'URAIAN' atau 'PEKERJAAN')
        header_row_index = -1
        found_cols = {}
        
        # Scan 20 baris pertama
        for idx, row in df_raw.head(25).iterrows():
            row_str = row.astype(str).str.upper().tolist()
            # Cek keyword
            if any("URAIAN" in s for s in row_str) or any("PEKERJAAN" in s for s in row_str):
                header_row_index = idx
                break
        
        if header_row_index == -1:
            st.error("Gagal menemukan header tabel (Kata Kunci: 'URAIAN' atau 'PEKERJAAN'). Pastikan file berisi tabel daftar harga.")
            return

        # 3. Reload DataFrame dengan Header yang benar
        if filename.endswith('.csv'):
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, header=header_row_index, on_bad_lines='skip')
        else:
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file, header=header_row_index)

        # 4. Mapping Kolom
        col_map = {}
        for c in df.columns:
            c_str = str(c).upper()
            if "URAIAN" in c_str or "PEKERJAAN" in c_str: col_map['Uraian'] = c
            if "SATUAN" in c_str: col_map['Satuan'] = c
            if "HARGA" in c_str and "JUMLAH" not in c_str: col_map['Harga'] = c
            if "KODE" in c_str or "NO" in c_str: col_map['Kode'] = c

        if 'Uraian' not in col_map or 'Harga' not in col_map:
            st.error(f"Kolom Uraian/Harga tidak terdeteksi. Kolom ditemukan: {list(df.columns)}")
            return

        # 5. Bersihkan Data
        df_clean = pd.DataFrame()
        df_clean['Uraian_Pekerjaan'] = df[col_map['Uraian']]
        df_clean['Satuan'] = df[col_map['Satuan']] if 'Satuan' in col_map else 'ls'
        
        # Bersihkan harga dari simbol Rp atau koma
        df_clean['Harga_Satuan'] = df[col_map['Harga']].astype(str).str.replace('Rp','').str.replace('.','').str.replace(',','.', regex=False)
        df_clean['Harga_Satuan'] = pd.to_numeric(df_clean['Harga_Satuan'], errors='coerce').fillna(0)
        
        # Buat Kode Unik
        if 'Kode' in col_map:
             df_clean['Kode_Analisa'] = df[col_map['Kode']].astype(str)
        else:
             df_clean['Kode_Analisa'] = ["IMP-" + str(i).zfill(3) for i in range(1, len(df_clean)+1)]

        df_clean = df_clean[df_clean['Harga_Satuan'] > 0] # Hanya ambil yg ada harganya
        df_clean = df_clean.drop_duplicates(subset=['Uraian_Pekerjaan'])

        # 6. Masukkan ke Sistem
        new_analysis = []
        new_prices = []
        
        for _, row in df_clean.iterrows():
            kode = str(row['Kode_Analisa']).strip()
            if len(kode) < 2 or kode == 'nan': continue
            
            uraian = str(row['Uraian_Pekerjaan']).strip()
            harsat = float(row['Harga_Satuan'])
            
            # Masukkan ke Harga Dasar (Reverse Overhead)
            harga_dasar = harsat / (1 + (st.session_state['global_overhead']/100))
            
            new_prices.append({
                'Kode': kode,
                'Komponen': uraian + " (Item Jadi)",
                'Satuan': row['Satuan'],
                'Harga_Dasar': harga_dasar,
                'Kategori': 'Material'
            })
            
            new_analysis.append({
                'Kode_Analisa': kode,
                'Uraian_Pekerjaan': uraian,
                'Komponen': uraian + " (Item Jadi)",
                'Koefisien': 1.0
            })
            
        if new_prices:
            st.session_state['df_prices'] = pd.concat([st.session_state['df_prices'], pd.DataFrame(new_prices)], ignore_index=True)
            st.session_state['df_analysis'] = pd.concat([st.session_state['df_analysis'], pd.DataFrame(new_analysis)], ignore_index=True)
            calculate_system()
            st.success(f"✅ Berhasil import {len(new_prices)} Item Pekerjaan!")
        else:
            st.warning("Data kosong setelah dibersihkan.")

    except Exception as e:
        st.error(f"Error Detail: {str(e)}")

# --- 4. Helper & UI ---
def to_excel_download(df, sheet_name="Sheet1"):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name=sheet_name)
    writer.close()
    return output.getvalue()

def render_print_button():
    st.markdown("""<style>@media print {div[data-testid="stSidebar"], header, footer {display: none;} .block-container {padding-top: 0;}}</style>""", unsafe_allow_html=True)
    components.html("<script>function cetak(){window.print()}</script><button onclick='cetak()'>🖨️ Print</button>", height=40)

# --- MAIN APP ---
def main():
    initialize_data()
    st.title("🏗️ SmartRAB-SNI (CSV Support)")
    
    tabs = st.tabs(["1. REKAPITULASI", "2. RAB PROYEK", "3. DATABASE HARGA (IMPORT)", "4. DATA"])

    # TAB 1
    with tabs[0]:
        st.header("Rekapitulasi Biaya")
        render_print_button()
        col1, col2 = st.columns([2,1])
        with col2:
             st.session_state['global_overhead'] = st.number_input("Overhead (%)", 0.0, 50.0, st.session_state['global_overhead'])
             if st.button("Hitung Ulang"): calculate_system(); st.rerun()
        with col1:
             if not st.session_state['df_rab'].empty:
                 rekap = st.session_state['df_rab'].groupby('Divisi')['Total_Harga'].sum().reset_index()
                 st.dataframe(rekap, use_container_width=True, hide_index=True, column_config={"Total_Harga": st.column_config.NumberColumn(format="Rp %d")})
                 st.metric("Total Biaya", f"Rp {rekap['Total_Harga'].sum():,.0f}")

    # TAB 2
    with tabs[1]:
        st.subheader("Input RAB")
        
        # Tambah Item
        with st.expander("➕ Tambah Pekerjaan", expanded=True):
            df_ref = st.session_state['df_analysis'][['Kode_Analisa', 'Uraian_Pekerjaan']].drop_duplicates()
            if not df_ref.empty:
                opts = dict(zip(df_ref['Kode_Analisa'], df_ref['Uraian_Pekerjaan']))
                c1, c2, c3 = st.columns([3, 1, 1])
                k_sel = c1.selectbox("Pilih Pekerjaan", opts.keys(), format_func=lambda x: f"{x} - {opts[x]}")
                vol = c2.number_input("Volume", 1.0)
                if c3.button("Tambah"):
                    new_row = {'No': len(st.session_state['df_rab'])+1, 'Divisi': 'UMUM', 'Uraian_Pekerjaan': opts[k_sel], 'Kode_Analisa_Ref': k_sel, 'Volume': vol, 'Harga_Satuan_Jadi':0, 'Total_Harga':0, 'Durasi_Minggu':1, 'Minggu_Mulai':1}
                    st.session_state['df_rab'] = pd.concat([st.session_state['df_rab'], pd.DataFrame([new_row])], ignore_index=True)
                    calculate_system()
                    st.rerun()
            else:
                st.warning("Database kosong. Import dulu di Tab 3.")

        # Tabel Editor
        edited = st.data_editor(st.session_state['df_rab'], use_container_width=True, num_rows="dynamic",
                                column_config={"Total_Harga": st.column_config.NumberColumn(format="Rp %d", disabled=True),
                                               "Harga_Satuan_Jadi": st.column_config.NumberColumn(format="Rp %d", disabled=True),
                                               "Kode_Analisa_Ref": st.column_config.TextColumn(disabled=True),
                                               "Uraian_Pekerjaan": st.column_config.TextColumn(disabled=True)})
        if not edited.equals(st.session_state['df_rab']):
            st.session_state['df_rab'] = edited
            calculate_system()
            st.rerun()

    # TAB 3 IMPORT
    with tabs[2]:
        st.header("📂 Import Database")
        st.info("Upload file 'Daftar Harga Satuan Pekerjaan.csv' di sini.")
        
        up_file = st.file_uploader("Upload CSV / Excel", type=['csv', 'xlsx'])
        if up_file and st.button("🚀 Proses Import"):
            smart_load_file(up_file)
            
        st.divider()
        st.write("Preview Data Analisa Saat Ini:")
        st.dataframe(st.session_state['df_analysis'], use_container_width=True)

    # TAB 4 DATA
    with tabs[3]:
        st.write("Data Harga Dasar & Analisa")
        st.dataframe(st.session_state['df_prices'])

if __name__ == "__main__":
    main()

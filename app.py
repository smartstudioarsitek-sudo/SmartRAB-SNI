import streamlit as st
import pandas as pd
import io
import xlsxwriter
import altair as alt
import difflib 
import os 

# --- Konfigurasi Halaman ---
st.set_page_config(page_title="SmartRAB-SNI Pro", layout="wide", page_icon="🏗️")

# --- Inisialisasi Session State ---
def initialize_session_state():
    defaults = {
        'global_overhead': 15.0,
        'project_name': 'Proyek Gedung Baru',
        'temp_template_list': [], 
        'df_rab': pd.DataFrame(columns=['No', 'Uraian Pekerjaan', 'Volume', 'Satuan', 'Harga Satuan', 'Total Harga', 'Lokasi']),
        'df_master': None 
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

initialize_session_state()

# --- Fungsi Helper: Membersihkan Data Master ---
def clean_master_data(df):
    try:
        # Hapus spasi di nama kolom
        df.columns = df.columns.str.strip().str.upper()
        
        # Cari kolom kunci (Fleksibel)
        col_no = next((c for c in df.columns if 'NO' in c), None)
        col_uraian = next((c for c in df.columns if 'URAIAN' in c), None)
        col_satuan = next((c for c in df.columns if 'SATUAN' in c), None)
        col_harga = next((c for c in df.columns if 'HARGA' in c), None)

        if not all([col_no, col_uraian, col_satuan, col_harga]):
            st.error(f"Format kolom tidak sesuai. Wajib ada: NO, URAIAN, SATUAN, HARGA. (Ditemukan: {df.columns.tolist()})")
            return pd.DataFrame()

        df_clean = df[[col_no, col_uraian, col_satuan, col_harga]].copy()
        df_clean.columns = ['NO', 'URAIAN PEKERJAAN', 'SATUAN', 'HARGA SATUAN']
        
        # Bersihkan data kosong
        df_clean = df_clean.dropna(subset=['URAIAN PEKERJAAN'])
        # Pastikan harga berupa angka
        df_clean['HARGA SATUAN'] = pd.to_numeric(df_clean['HARGA SATUAN'], errors='coerce').fillna(0)
        df_clean['NO'] = df_clean['NO'].astype(str)
        
        return df_clean
    except Exception as e:
        st.error(f"Gagal memproses data: {e}")
        return pd.DataFrame()

# --- Fungsi Load Database Master (Auto-Detect) ---
def load_master_database_local():
    # Daftar kemungkinan nama file (Prioritas sesuai file Kakak)
    possible_names = [
        "data_rab.xlsx - Daftar Harga Satuan Pekerjaan.csv",
        "Daftar Harga Satuan Pekerjaan.csv",
        "data_rab.csv"
    ]
    
    for name in possible_names:
        if os.path.exists(name):
            try:
                # Header ada di baris ke-6 (index 5)
                df = pd.read_csv(name, header=5)
                clean_df = clean_master_data(df)
                if not clean_df.empty:
                    st.toast(f"✅ Database otomatis dimuat: {name}")
                    return clean_df
            except Exception as e:
                print(f"Gagal baca {name}: {e}")
                continue
    return None

# Coba load otomatis saat aplikasi mulai
if st.session_state['df_master'] is None:
    loaded_df = load_master_database_local()
    if loaded_df is not None:
        st.session_state['df_master'] = loaded_df

# --- MODUL 1: Generator Template Excel ---
def generate_smart_volume_template(prefilled_data=None):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    ws_input = workbook.add_worksheet('Input Volume')
    ws_ref = workbook.add_worksheet('Reference_DB') 
    
    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#4F81BD', 'font_color': 'white', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
    headers = ['KODE_ANALISA', 'URAIAN_PEKERJAAN', 'LOKASI_ZONA', 'PANJANG', 'LEBAR', 'TINGGI', 'JUMLAH_UNIT', 'SATUAN', 'VOLUME_MANUAL', 'KETERANGAN']
    ws_input.write_row('A1', headers, header_fmt)
    ws_input.set_column('B:B', 50) 
    
    # Isi Data Referensi untuk Dropdown
    df_ref = st.session_state['df_master']
    if df_ref is not None and not df_ref.empty:
        ws_ref.write_row('A1', ['KODE', 'URAIAN', 'SATUAN'])
        for i, row in df_ref.iterrows():
            ws_ref.write(i+1, 0, str(row['NO']))
            ws_ref.write(i+1, 1, str(row['URAIAN PEKERJAAN']))
            ws_ref.write(i+1, 2, str(row['SATUAN']))
        ws_ref.hide()
        
        # Validasi Data (Dropdown)
        data_len = len(df_ref)
        ws_input.data_validation(f'B2:B{data_len+100}', {'validate': 'list', 'source': f'=Reference_DB!$B$2:$B${data_len+1}'})
        ws_input.data_validation('H2:H1000', {'validate': 'list', 'source': ['m3', 'm2', 'm1', 'kg', 'bh', 'ls', 'unit', 'set', 'titik']})

    # Isi Data Pre-filled (dari Pencarian)
    if prefilled_data:
        for idx, item in enumerate(prefilled_data):
            row = idx + 1
            ws_input.write(row, 0, item['NO'])
            ws_input.write(row, 1, item['URAIAN'])
            ws_input.write(row, 6, 1)
            ws_input.write(row, 7, item['SATUAN'])
            
    workbook.close()
    output.seek(0)
    return output

# --- MODUL 2: Mesin Import Cerdas (Fuzzy Logic) ---
def process_smart_import(uploaded_file):
    try:
        df_import = pd.read_excel(uploaded_file, sheet_name='Input Volume')
        master_db = st.session_state['df_master']
        results = []
        
        for index, row in df_import.iterrows():
            if pd.isna(row['URAIAN_PEKERJAAN']): continue
            
            kode = str(row['KODE_ANALISA']) if pd.notnull(row['KODE_ANALISA']) else ''
            uraian_input = str(row['URAIAN_PEKERJAAN'])
            
            # Kalkulasi Volume
            vol_manual = row.get('VOLUME_MANUAL', 0)
            if pd.notnull(vol_manual) and vol_manual != 0:
                volume_final = vol_manual
            else:
                p = row.get('PANJANG', 0) if pd.notnull(row.get('PANJANG')) else 1
                l = row.get('LEBAR', 0) if pd.notnull(row.get('LEBAR')) else 1
                t = row.get('TINGGI', 0) if pd.notnull(row.get('TINGGI')) else 1
                jml = row.get('JUMLAH_UNIT', 1) if pd.notnull(row.get('JUMLAH_UNIT')) else 1
                
                # Cek jika semua dimensi kosong
                if pd.isna(row.get('PANJANG')) and pd.isna(row.get('LEBAR')): 
                    volume_final = jml 
                else: 
                    volume_final = p * l * t * jml

            # Logika Pencocokan (Matching)
            match_row = pd.DataFrame()
            status_match = "Baru"
            
            # 1. Cek Kode (Deterministik)
            if kode != '' and kode != 'nan':
                match_row = master_db[master_db['NO'] == kode]
                if not match_row.empty: status_match = "Terkunci (Kode)"

            # 2. Cek Nama (Fuzzy Logic)
            if match_row.empty:
                matches = difflib.get_close_matches(uraian_input, master_db['URAIAN PEKERJAAN'].astype(str), n=1, cutoff=0.7)
                if matches:
                    match_row = master_db[master_db['URAIAN PEKERJAAN'] == matches[0]]
                    status_match = "Otomatis (Fuzzy)"
                else:
                    status_match = "Manual (Tidak Ditemukan)"
            
            # Ambil Harga
            if not match_row.empty:
                harga_satuan = match_row.iloc[0]['HARGA SATUAN']
                satuan_resmi = match_row.iloc[0]['SATUAN']
                uraian_resmi = match_row.iloc[0]['URAIAN PEKERJAAN']
                kode_resmi = match_row.iloc[0]['NO']
            else:
                harga_satuan = 0
                satuan_resmi = row['SATUAN']
                uraian_resmi = uraian_input
                kode_resmi = "MANUAL"

            results.append({
                'No': kode_resmi, 
                'Uraian Pekerjaan': uraian_resmi, 
                'Lokasi': row.get('LOKASI_ZONA', '-'),
                'Volume': volume_final, 
                'Satuan': satuan_resmi, 
                'Harga Satuan': harga_satuan,
                'Total Harga': volume_final * harga_satuan, 
                'Metode Match': status_match
            })
        return pd.DataFrame(results)
    except Exception as e:
        st.error(f"Error Import: {e}")
        return None

# --- UI UTAMA ---
def main():
    st.title("💰 SmartRAB - Estimasi Biaya Cerdas")
    
    # --- Sidebar ---
    with st.sidebar:
        st.header("📋 Data Proyek")
        st.session_state['project_name'] = st.text_input("Nama Proyek", st.session_state['project_name'])
        st.session_state['global_overhead'] = st.number_input("Profit (%)", value=15.0)
        
        st.markdown("---")
        st.subheader("📂 Database Master")
        
        # STATUS DATABASE
        if st.session_state['df_master'] is None:
            st.error("❌ Database Belum Terbaca")
            st.info("Sistem tidak menemukan file otomatis. Silakan upload manual di bawah ini:")
            
            # FITUR UPLOAD MANUAL (Solusi Error)
            uploaded_master = st.file_uploader("Upload 'data_rab.xlsx - Daftar Harga Satuan Pekerjaan.csv'", type=['csv'])
            if uploaded_master:
                # Baca header baris ke-6 (index 5) sesuai file Kakak
                df_uploaded = pd.read_csv(uploaded_master, header=5) 
                df_clean = clean_master_data(df_uploaded)
                if not df_clean.empty:
                    st.session_state['df_master'] = df_clean
                    st.success("Database berhasil dimuat manual!")
                    st.rerun()
        else:
            st.success(f"✅ Database Aktif: {len(st.session_state['df_master'])} Item")
            if st.button("🔄 Reset / Ganti Database"):
                st.session_state['df_master'] = None
                st.rerun()

    # --- BLOCKING: JIKA DB KOSONG, STOP DI SINI ---
    if st.session_state['df_master'] is None:
        st.warning("👈 Mohon Upload File Database Harga Satuan di Sidebar sebelah kiri untuk memulai.")
        st.stop()

    # --- TABS APLIKASI ---
    tabs = st.tabs(["📊 RAB & Import", "🔎 Database Harga", "📈 Rekapitulasi"])

    # TAB 1: RAB & Import
    with tabs[0]:
        col_search, col_action = st.columns([2, 1])
        with col_search:
            st.subheader("1. Cari & Pilih Pekerjaan")
            st.caption("Cari pekerjaan dari database, lalu tambahkan ke list untuk dibuatkan Template Excel.")
            search_txt = st.text_input("Kata Kunci (Contoh: Beton, Dinding, Cat)", placeholder="Ketik disini...")
            
            if search_txt:
                df_master = st.session_state['df_master']
                mask = df_master['URAIAN PEKERJAAN'].str.contains(search_txt, case=False, na=False)
                df_results = df_master[mask].head(10)
                if not df_results.empty:
                    st.dataframe(df_results[['NO', 'URAIAN PEKERJAAN', 'HARGA SATUAN']], hide_index=True, use_container_width=True)
                    
                    pilihan = st.selectbox("Pilih Item:", df_results['URAIAN PEKERJAAN'])
                    if st.button("➕ Tambah ke List Template"):
                        item = df_results[df_results['URAIAN PEKERJAAN'] == pilihan].iloc[0]
                        st.session_state['temp_template_list'].append({'NO': item['NO'], 'URAIAN': item['URAIAN PEKERJAAN'], 'SATUAN': item['SATUAN']})
                        st.success(f"Berhasil ditambahkan: {pilihan}")
                else:
                    st.warning("Tidak ditemukan.")

        with col_action:
            st.subheader("2. Download Template")
            st.info("List pekerjaan yang sudah dipilih:")
            if st.session_state['temp_template_list']:
                st.write(pd.DataFrame(st.session_state['temp_template_list'])[['URAIAN']])
                if st.button("Hapus Semua List"):
                     st.session_state['temp_template_list'] = []
                     st.rerun()
            else:
                st.write("*Belum ada item dipilih*")
            
            excel_data = generate_smart_volume_template(st.session_state['temp_template_list'])
            st.download_button("📥 Download Excel Template", excel_data, "Template_Volume_RAB.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

        st.markdown("---")
        st.subheader("3. Upload Template & Hitung RAB")
        uploaded_rab = st.file_uploader("Upload Excel Template yang sudah diisi Volume-nya", type=['xlsx'])
        if uploaded_rab:
            with st.spinner("Sedang menghitung..."):
                df_hasil = process_smart_import(uploaded_rab)
                if df_hasil is not None:
                    st.session_state['df_rab'] = df_hasil
                    st.success("Perhitungan Selesai!")
                    st.dataframe(df_hasil.style.format({"Harga Satuan": "{:,.0f}", "Total Harga": "{:,.0f}", "Volume": "{:.2f}"}), use_container_width=True)
                    
                    total_rab = df_hasil['Total Harga'].sum()
                    st.markdown(f"### Total Estimasi Fisik: Rp {total_rab:,.0f}")

    # TAB 2: Database
    with tabs[1]:
        st.dataframe(st.session_state['df_master'], use_container_width=True)

    # TAB 3: Rekap
    with tabs[2]:
        df_rab = st.session_state['df_rab']
        if not df_rab.empty:
            st.header("Rekapitulasi Akhir")
            total_real = df_rab['Total Harga'].sum()
            overhead = total_real * (st.session_state['global_overhead']/100)
            grand_total = total_real + overhead
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Biaya Real", f"Rp {total_real:,.0f}")
            c2.metric(f"Profit ({st.session_state['global_overhead']}%)", f"Rp {overhead:,.0f}")
            c3.metric("HARGA PENAWARAN", f"Rp {grand_total:,.0f}", delta="Final")
            
            # Pie Chart Per Lokasi
            if 'Lokasi' in df_rab.columns:
                chart_data = df_rab.groupby('Lokasi')['Total Harga'].sum().reset_index()
                chart = alt.Chart(chart_data).mark_arc().encode(
                    theta='Total Harga',
                    color='Lokasi',
                    tooltip=['Lokasi', 'Total Harga']
                )
                st.altair_chart(chart, use_container_width=True)

if __name__ == "__main__":
    main()

import streamlit as st
import pandas as pd
import io
import xlsxwriter
import altair as alt
import difflib # Library untuk pencocokan teks (Fuzzy Logic)

# --- Konfigurasi Halaman ---
st.set_page_config(page_title="SmartRAB-SNI Pro", layout="wide", page_icon="🏗️")

# --- Inisialisasi Session State ---
def initialize_session_state():
    defaults = {
        'global_overhead': 15.0,
        'project_name': 'Proyek Gedung Baru',
        'temp_template_list': [], # Untuk menyimpan item sementara sebelum download template
        'df_rab': pd.DataFrame(columns=['No', 'Uraian Pekerjaan', 'Volume', 'Satuan', 'Harga Satuan', 'Total Harga', 'Bobot']),
        'df_master': None # Tempat menyimpan database harga
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

initialize_session_state()

# --- Fungsi Load Database Master (PENTING) ---
@st.cache_data
def load_master_database():
    try:
        # Membaca CSV Master (Header ada di baris ke-6 atau index 5)
        # Pastikan nama file sesuai dengan yang diupload
        filename = "data_rab.xlsx - Daftar Harga Satuan Pekerjaan.csv"
        df = pd.read_csv(filename, header=5)
        
        # Ambil kolom penting saja dan bersihkan
        df_clean = df[['NO', 'URAIAN PEKERJAAN', 'SATUAN', 'HARGA SATUAN']].dropna(subset=['URAIAN PEKERJAAN'])
        
        # Pastikan kolom harga numerik
        df_clean['HARGA SATUAN'] = pd.to_numeric(df_clean['HARGA SATUAN'], errors='coerce').fillna(0)
        df_clean['NO'] = df_clean['NO'].astype(str)
        
        return df_clean
    except Exception as e:
        st.error(f"Gagal memuat Database Referensi: {e}")
        return pd.DataFrame() # Return empty DF jika gagal

# Load data ke session state saat aplikasi mulai
if st.session_state['df_master'] is None:
    st.session_state['df_master'] = load_master_database()

# --- MODUL 1: Generator Template Excel Cerdas ---
def generate_smart_volume_template(prefilled_data=None):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    # 1. Sheet Input Utama
    ws_input = workbook.add_worksheet('Input Volume')
    # 2. Sheet Referensi (Disembunyikan)
    ws_ref = workbook.add_worksheet('Reference_DB') 
    
    # Format Header Visual
    header_fmt = workbook.add_format({
        'bold': True, 'bg_color': '#4F81BD', 'font_color': 'white', 
        'border': 1, 'align': 'center', 'valign': 'vcenter'
    })
    
    # Kolom Template
    headers = [
        'KODE_ANALISA',       # A: Hidden ID
        'URAIAN_PEKERJAAN',   # B: Input User/Dropdown
        'LOKASI_ZONA',        # C: Lantai 1, dst
        'PANJANG',            # D
        'LEBAR',              # E
        'TINGGI',             # F
        'JUMLAH_UNIT',        # G
        'SATUAN',             # H
        'VOLUME_MANUAL',      # I: Override jika rumus tidak baku
        'KETERANGAN'          # J
    ]
    
    ws_input.write_row('A1', headers, header_fmt)
    
    # Atur Lebar Kolom
    ws_input.set_column('A:A', 15) # Kode
    ws_input.set_column('B:B', 50) # Uraian (Lebar)
    ws_input.set_column('C:C', 15) # Lokasi
    ws_input.set_column('D:G', 10) # Dimensi
    
    # --- Isi Sheet Referensi untuk Dropdown ---
    df_ref = st.session_state['df_master']
    if not df_ref.empty:
        ws_ref.write_row('A1', ['KODE', 'URAIAN', 'SATUAN'])
        for i, row in df_ref.iterrows():
            ws_ref.write(i+1, 0, str(row['NO']))
            ws_ref.write(i+1, 1, str(row['URAIAN PEKERJAAN']))
            ws_ref.write(i+1, 2, str(row['SATUAN']))
        
        # Sembunyikan sheet referensi agar rapi
        ws_ref.hide()
        
        # Buat Data Validation (Dropdown) di Kolom Uraian (B)
        data_len = len(df_ref)
        ws_input.data_validation(f'B2:B{data_len+100}', {
            'validate': 'list',
            'source': f'=Reference_DB!$B$2:$B${data_len+1}'
        })
        
        # Dropdown Satuan Standar
        ws_input.data_validation('H2:H1000', {
            'validate': 'list',
            'source': ['m3', 'm2', 'm1', 'kg', 'bh', 'ls', 'unit', 'set', 'titik']
        })

    # --- Pre-filling Data (Jika user memilih dari Search UI) ---
    if prefilled_data:
        for idx, item in enumerate(prefilled_data):
            row = idx + 1
            ws_input.write(row, 0, item['NO'])      # Kode Analisa (Hidden Key)
            ws_input.write(row, 1, item['URAIAN'])  # Nama Pekerjaan
            ws_input.write(row, 6, 1)               # Default Jumlah = 1
            ws_input.write(row, 7, item['SATUAN'])  # Satuan
            
    workbook.close()
    output.seek(0)
    return output

# --- MODUL 2: Mesin Import Cerdas (Fuzzy Logic) ---
def process_smart_import(uploaded_file):
    try:
        # Baca Excel
        df_import = pd.read_excel(uploaded_file, sheet_name='Input Volume')
        master_db = st.session_state['df_master']
        
        results = []
        
        # Iterasi setiap baris input
        for index, row in df_import.iterrows():
            # Skip baris kosong total
            if pd.isna(row['URAIAN_PEKERJAAN']):
                continue
                
            kode = str(row['KODE_ANALISA']) if pd.notnull(row['KODE_ANALISA']) else ''
            uraian_input = str(row['URAIAN_PEKERJAAN'])
            
            # 1. Kalkulasi Volume Geometris
            # Jika user mengisi 'VOLUME_MANUAL', pakai itu. Jika tidak, hitung PxLxTxJml
            vol_manual = row.get('VOLUME_MANUAL', 0)
            if pd.notnull(vol_manual) and vol_manual != 0:
                volume_final = vol_manual
            else:
                p = row.get('PANJANG', 0) if pd.notnull(row.get('PANJANG')) else 1
                l = row.get('LEBAR', 0) if pd.notnull(row.get('LEBAR')) else 1
                t = row.get('TINGGI', 0) if pd.notnull(row.get('TINGGI')) else 1
                jml = row.get('JUMLAH_UNIT', 1) if pd.notnull(row.get('JUMLAH_UNIT')) else 1
                
                # Handle jika dimensi kosong (anggap 1 untuk perkalian, kecuali semua kosong)
                if row.get('PANJANG') is None and row.get('LEBAR') is None:
                    volume_final = jml # Asumsi input langsung jumlah
                else:
                    volume_final = p * l * t * jml

            # 2. Logika Pencocokan (Matching)
            match_row = pd.DataFrame()
            status_match = "Baru"
            
            # A. Cek Deterministik (Berdasarkan Kode)
            if kode != '' and kode != 'nan':
                match_row = master_db[master_db['NO'] == kode]
                if not match_row.empty:
                    status_match = "Terkunci (Kode)"

            # B. Cek Fuzzy (Berdasarkan Kemiripan Nama) jika Kode gagal
            if match_row.empty:
                # Cari kemiripan teks > 70%
                matches = difflib.get_close_matches(uraian_input, master_db['URAIAN PEKERJAAN'].astype(str), n=1, cutoff=0.7)
                
                if matches:
                    matched_uraian = matches[0]
                    match_row = master_db[master_db['URAIAN PEKERJAAN'] == matched_uraian]
                    status_match = "Otomatis (Fuzzy)"
                else:
                    status_match = "Manual (Tidak Ditemukan)"
            
            # 3. Ambil Harga & Data Final
            if not match_row.empty:
                harga_satuan = match_row.iloc[0]['HARGA SATUAN']
                satuan_resmi = match_row.iloc[0]['SATUAN']
                uraian_resmi = match_row.iloc[0]['URAIAN PEKERJAAN']
                kode_resmi = match_row.iloc[0]['NO']
            else:
                # Jika tidak ketemu di DB, pakai input user
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
        st.error(f"Terjadi kesalahan saat membaca file: {e}")
        return None

def main():
    st.title("💰 SmartRAB - Estimasi Biaya Cerdas")
    st.markdown("---")

    # --- Sidebar: Profil Proyek ---
    with st.sidebar:
        st.header("📋 Data Proyek")
        st.session_state['project_name'] = st.text_input("Nama Proyek", st.session_state['project_name'])
        st.session_state['global_overhead'] = st.number_input("Profit & Overhead (%)", value=15.0)
        
        st.info("""
        **Panduan Fitur Baru:**
        1. Gunakan **Pencarian** di Tab RAB untuk memilih pekerjaan.
        2. Download **Template Cerdas**.
        3. Isi volume di Excel.
        4. Upload kembali untuk **Hitung Otomatis**.
        """)

    # --- TAB NAVIGASI UTAMA ---
    tabs = st.tabs(["📊 RAB & Import", "🔎 Database Harga", "📈 Rekapitulasi"])

    # === TAB 1: RAB & FITUR PENCARIAN ===
    with tabs[0]:
        col_search, col_action = st.columns([2, 1])
        
        # --- A. Fitur Pencarian & Tambah ke Template ---
        with col_search:
            st.subheader("1. Cari Item Pekerjaan (Pre-Planning)")
            search_txt = st.text_input("Ketik nama pekerjaan (misal: 'Beton', 'Dinding', 'Kabel')", placeholder="Cari di database SNI...")
            
            if search_txt:
                df_master = st.session_state['df_master']
                # Filter data
                mask = df_master['URAIAN PEKERJAAN'].str.contains(search_txt, case=False, na=False)
                df_results = df_master[mask].head(10) # Tampilkan 10 hasil teratas
                
                if not df_results.empty:
                    # Tampilkan hasil pencarian
                    st.dataframe(df_results[['NO', 'URAIAN PEKERJAAN', 'SATUAN', 'HARGA SATUAN']], hide_index=True, use_container_width=True)
                    
                    # Dropdown untuk memilih
                    pilihan = st.selectbox("Pilih untuk ditambahkan ke Template:", df_results['URAIAN PEKERJAAN'])
                    
                    if st.button("➕ Tambahkan ke List Template"):
                        # Ambil data lengkap item yang dipilih
                        item_data = df_results[df_results['URAIAN PEKERJAAN'] == pilihan].iloc[0]
                        st.session_state['temp_template_list'].append({
                            'NO': item_data['NO'],
                            'URAIAN': item_data['URAIAN PEKERJAAN'],
                            'SATUAN': item_data['SATUAN']
                        })
                        st.success(f"Berhasil menambahkan: {pilihan}")
                else:
                    st.warning("Pekerjaan tidak ditemukan.")

        # --- B. List Sementara & Download ---
        with col_action:
            st.subheader("2. Download Template")
            jml_item = len(st.session_state['temp_template_list'])
            st.metric("Item di Keranjang", f"{jml_item} Item")
            
            if st.checkbox("Lihat List Item"):
                st.write(st.session_state['temp_template_list'])
                if st.button("Hapus Semua List"):
                    st.session_state['temp_template_list'] = []
                    st.rerun()

            # Tombol Generate Excel
            excel_data = generate_smart_volume_template(st.session_state['temp_template_list'])
            st.download_button(
                label="📥 Download Template Excel",
                data=excel_data,
                file_name="Template_Hitung_Volume.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

        st.markdown("---")
        
        # --- C. Upload & Proses ---
        st.subheader("3. Upload Template & Hitung RAB")
        uploaded_file = st.file_uploader("Upload file Excel yang sudah diisi volumenya", type=['xlsx'])
        
        if uploaded_file:
            with st.spinner("Sedang membaca file & mencocokkan database..."):
                # Panggil Fungsi Modul 2
                df_hasil = process_smart_import(uploaded_file)
                
                if df_hasil is not None:
                    # Update Session State RAB
                    st.session_state['df_rab'] = df_hasil
                    
                    # Tampilkan Hasil
                    st.success("Perhitungan Selesai!")
                    
                    # Ringkasan Match
                    n_auto = len(df_hasil[df_hasil['Metode Match'] == 'Otomatis (Fuzzy)'])
                    n_code = len(df_hasil[df_hasil['Metode Match'] == 'Terkunci (Kode)'])
                    n_manual = len(df_hasil[df_hasil['Metode Match'] == 'Manual (Tidak Ditemukan)'])
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Match Kode (Akurat)", n_code)
                    c2.metric("Match Fuzzy (Cerdas)", n_auto)
                    c3.metric("Manual/Tidak Ketemu", n_manual)
                    
                    # Tampilan Tabel Utama
                    st.dataframe(
                        df_hasil.style.format({"Harga Satuan": "Rp {:,.0f}", "Total Harga": "Rp {:,.0f}", "Volume": "{:.2f}"}),
                        use_container_width=True
                    )
                    
                    # Hitung Grand Total
                    grand_total = df_hasil['Total Harga'].sum()
                    st.markdown(f"### Total Biaya Konstruksi: **Rp {grand_total:,.0f}**")

    # === TAB 2: DATABASE ===
    with tabs[1]:
        st.header("Database Harga Satuan (DHSP)")
        if st.session_state['df_master'] is not None:
            st.dataframe(st.session_state['df_master'], use_container_width=True)
        else:
            st.error("Database belum dimuat. Pastikan file CSV tersedia.")

    # === TAB 3: REKAPITULASI ===
    with tabs[2]:
        st.header("Rekapitulasi Biaya")
        df_rab = st.session_state['df_rab']
        
        if not df_rab.empty:
            # Grouping by Lokasi/Lantai
            rekap_lokasi = df_rab.groupby('Lokasi')['Total Harga'].sum().reset_index()
            
            col_chart, col_df = st.columns(2)
            
            with col_chart:
                chart = alt.Chart(rekap_lokasi).mark_arc(innerRadius=50).encode(
                    theta='Total Harga',
                    color='Lokasi',
                    tooltip=['Lokasi', 'Total Harga']
                ).properties(title="Proporsi Biaya per Zona")
                st.altair_chart(chart, use_container_width=True)
            
            with col_df:
                st.dataframe(rekap_lokasi.style.format({"Total Harga": "Rp {:,.0f}"}), use_container_width=True)
                
                # Biaya + Overhead
                real_cost = df_rab['Total Harga'].sum()
                overhead_val = real_cost * (st.session_state['global_overhead'] / 100)
                final_total = real_cost + overhead_val
                
                st.write("---")
                st.write(f"Biaya Real: Rp {real_cost:,.0f}")
                st.write(f"Jasa & Overhead ({st.session_state['global_overhead']}%): Rp {overhead_val:,.0f}")
                st.markdown(f"### HARGA PENAWARAN: Rp {final_total:,.0f}")

# Menjalankan Aplikasi
if __name__ == "__main__":
    main()

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

    # Database Standar (Default)
    if 'df_prices' not in st.session_state:
        data_prices = {
            'Kode': ['M.01', 'M.02', 'L.01', 'L.02'],
            'Komponen': ['Semen Portland', 'Pasir Beton', 'Pekerja', 'Tukang Batu'],
            'Satuan': ['kg', 'kg', 'OH', 'OH'],
            'Harga_Dasar': [1300, 300, 100000, 145000],
            'Kategori': ['Material', 'Material', 'Upah', 'Upah']
        }
        st.session_state['df_prices'] = pd.DataFrame(data_prices)

    if 'df_analysis' not in st.session_state:
        # Data Dummy awal
        data_analysis = {
            'Kode_Analisa': ['A.2.2.1', 'A.2.2.1', 'A.2.2.1', 'A.2.2.1'],
            'Uraian_Pekerjaan': ['Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4', 'Pondasi Batu Kali 1:4'],
            'Komponen': ['Batu Kali', 'Semen Portland', 'Pasir Beton', 'Pekerja'],
            'Koefisien': [1.2, 163.0, 0.52, 1.5]
        }
        st.session_state['df_analysis'] = pd.DataFrame(data_analysis)

    if 'df_rab' not in st.session_state:
        # Struktur RAB Kosong
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

    # Normalisasi Key untuk Join
    df_p['Key'] = df_p['Komponen'].str.strip().str.lower()
    df_a['Key'] = df_a['Komponen'].str.strip().str.lower()

    # 1. Hitung Harga Satuan
    merged_analysis = pd.merge(df_a, df_p[['Key', 'Harga_Dasar', 'Satuan', 'Kategori']], on='Key', how='left')
    merged_analysis['Harga_Dasar'] = merged_analysis['Harga_Dasar'].fillna(0)
    merged_analysis['Subtotal'] = merged_analysis['Koefisien'] * merged_analysis['Harga_Dasar']
    
    st.session_state['df_analysis_detailed'] = merged_analysis 

    unit_prices_pure = merged_analysis.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices_pure['Harga_Kalkulasi'] = unit_prices_pure['Subtotal'] * overhead_factor 
    
    # 2. Update RAB (Join dengan Harsat)
    # Pastikan tipe data string agar tidak error merge
    df_r['Kode_Analisa_Ref'] = df_r['Kode_Analisa_Ref'].astype(str).str.strip()
    unit_prices_pure['Kode_Analisa'] = unit_prices_pure['Kode_Analisa'].astype(str).str.strip()
    
    df_r_temp = pd.merge(df_r, unit_prices_pure[['Kode_Analisa', 'Harga_Kalkulasi']], left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
    
    # Jika Harga Kalkulasi NaN (tidak ada di analisa), biarkan 0 atau ambil dari manual input jika nanti ada fitur itu
    df_r['Harga_Satuan_Jadi'] = df_r_temp['Harga_Kalkulasi'].fillna(0)
    df_r['Total_Harga'] = df_r['Volume'] * df_r['Harga_Satuan_Jadi']
    st.session_state['df_rab'] = df_r

    # 3. Rekap Material
    if not df_r.empty:
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
        st.session_state['df_material_rekap'] = pd.DataFrame()

# --- 3. Fungsi Load Master Database (FITUR BARU) ---
def process_uploaded_master(file):
    try:
        xls = pd.ExcelFile(file)
        sheet_names = xls.sheet_names
        
        # Coba cari sheet yang mengandung kata "Harga" atau "Daftar"
        target_sheet = None
        for s in sheet_names:
            if "harga" in s.lower() or "daftar" in s.lower():
                target_sheet = s
                break
        
        if not target_sheet:
            target_sheet = sheet_names[0] # Fallback ke sheet pertama
        
        df = pd.read_excel(file, sheet_name=target_sheet)
        
        # Bersihkan Data: Cari kolom yang relevan
        # Kita cari kolom yg mirip 'Uraian', 'Satuan', 'Harga'
        col_map = {}
        for c in df.columns:
            c_low = str(c).lower()
            if 'uraian' in c_low or 'pekerjaan' in c_low: col_map['Uraian'] = c
            if 'satuan' in c_low: col_map['Satuan'] = c
            if 'harga' in c_low and 'jumlah' not in c_low: col_map['Harga'] = c
            if 'kode' in c_low or 'no' in c_low: col_map['Kode'] = c

        if 'Uraian' in col_map and 'Harga' in col_map:
            # Standardisasi DataFrame
            df_clean = pd.DataFrame()
            df_clean['Uraian_Pekerjaan'] = df[col_map['Uraian']]
            df_clean['Satuan'] = df[col_map.get('Satuan', df.columns[1])] # Asumsi kolom 2 jika gak nemu
            df_clean['Harga_Satuan'] = pd.to_numeric(df[col_map['Harga']], errors='coerce').fillna(0)
            
            if 'Kode' in col_map:
                df_clean['Kode_Analisa'] = df[col_map['Kode']].astype(str)
            else:
                # Generate Kode Otomatis jika tidak ada
                df_clean['Kode_Analisa'] = ["IMP." + str(i).zfill(3) for i in range(1, len(df_clean)+1)]

            df_clean = df_clean.dropna(subset=['Uraian_Pekerjaan'])
            
            # --- INTEGRASI KE SISTEM ---
            # Kita masukkan data ini ke df_analysis dan df_prices sebagai "Item Jadi"
            # Agar sistem kalkulasi tetap jalan, kita anggap ini adalah Analisa dengan 1 komponen
            
            new_analysis_rows = []
            new_price_rows = []
            
            existing_codes = st.session_state['df_analysis']['Kode_Analisa'].unique()
            
            for index, row in df_clean.iterrows():
                kode = str(row['Kode_Analisa']).strip()
                if kode in existing_codes or row['Harga_Satuan'] <= 0:
                    continue # Skip jika duplikat atau harga 0
                
                uraian = row['Uraian_Pekerjaan']
                
                # Tambah ke Master Harga (Komponen = Uraian Pekerjaan itu sendiri)
                new_price_rows.append({
                    'Kode': kode,
                    'Komponen': uraian + " (Mat)", # Penanda
                    'Satuan': str(row['Satuan']),
                    'Harga_Dasar': row['Harga_Satuan'] / (1 + (st.session_state['global_overhead']/100)), # Reverse Engineer Overhead
                    'Kategori': 'Material' # Default
                })
                
                # Tambah ke Analisa (1 Komponen, Koef 1)
                new_analysis_rows.append({
                    'Kode_Analisa': kode,
                    'Uraian_Pekerjaan': uraian,
                    'Komponen': uraian + " (Mat)",
                    'Koefisien': 1.0
                })

            if new_price_rows:
                df_prices_new = pd.DataFrame(new_price_rows)
                st.session_state['df_prices'] = pd.concat([st.session_state['df_prices'], df_prices_new], ignore_index=True)
                
                df_analysis_new = pd.DataFrame(new_analysis_rows)
                st.session_state['df_analysis'] = pd.concat([st.session_state['df_analysis'], df_analysis_new], ignore_index=True)
                
                calculate_system()
                st.success(f"Berhasil mengimpor {len(new_price_rows)} item pekerjaan dari Excel!")
            else:
                st.warning("Tidak ada data baru yang valid diimpor (Mungkin duplikat atau format tidak terbaca).")
        else:
            st.error("Gagal mendeteksi kolom 'Uraian' dan 'Harga' di file Excel. Pastikan ada header kolom tersebut.")

    except Exception as e:
        st.error(f"Error membaca file: {e}")

# --- 4. Logic Kurva S (Sama) ---
def generate_s_curve_data():
    df = st.session_state['df_rab'].copy()
    grand_total = df['Total_Harga'].sum()
    if grand_total == 0: return None, None

    df['Bobot_Pct'] = (df['Total_Harga'] / grand_total) * 100
    max_week = int(df.apply(lambda x: x['Minggu_Mulai'] + x['Durasi_Minggu'] - 1, axis=1).max())
    if pd.isna(max_week) or max_week < 1: max_week = 1
    
    cumulative_list = []
    cumulative_progress = 0
    for w in range(1, max_week + 2):
        weekly_weight = 0
        for _, row in df.iterrows():
            start = row['Minggu_Mulai']
            end = start + row['Durasi_Minggu'] - 1
            if start <= w <= end:
                weekly_weight += (row['Bobot_Pct'] / row['Durasi_Minggu'])
        
        cumulative_progress += weekly_weight
        cumulative_list.append({'Minggu': f"M{w}", 'Minggu_Int': w, 'Rencana_Kumulatif': min(cumulative_progress, 100)})

    return df, pd.DataFrame(cumulative_list)

# --- UI Helpers ---
def to_excel_download(df, sheet_name="Sheet1"):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name=sheet_name)
    writer.close()
    return output.getvalue()

def render_print_button():
    st.markdown("""<style>@media print {div[data-testid="stSidebar"], header, footer {display: none;} .block-container {padding-top: 0;}}</style>""", unsafe_allow_html=True)
    if st.button("🖨️ Cetak / Print PDF"):
        components.html("<script>window.print()</script>", height=0)

# --- MAIN APPLICATION ---
def main():
    initialize_data()
    st.title("🏗️ SmartRAB-SNI Pro")
    st.caption("Aplikasi RAB dengan Integrasi Database Excel")

    tabs = st.tabs([
        "📊 REKAPITULASI", 
        "📝 RAB PROYEK", 
        "📚 DATABASE AHSP", 
        "🔍 DETAIL ANALISA", 
        "💰 SUMBER HARGA", 
        "📈 KURVA S"
    ])

    # === TAB 1: REKAPITULASI ===
    with tabs[0]:
        st.header("Rekapitulasi Biaya")
        render_print_button()
        
        col1, col2 = st.columns([2, 1])
        with col2:
            st.info("Pengaturan Proyek")
            st.session_state['project_name'] = st.text_input("Nama Proyek", st.session_state['project_name'])
            st.session_state['project_loc'] = st.text_input("Lokasi", st.session_state['project_loc'])
            ov = st.number_input("Overhead (%)", 0.0, 50.0, st.session_state['global_overhead'])
            if ov != st.session_state['global_overhead']:
                st.session_state['global_overhead'] = ov
                calculate_system()
                st.rerun()

        with col1:
            df_rab = st.session_state['df_rab']
            if not df_rab.empty and 'Divisi' in df_rab.columns:
                rekap = df_rab.groupby('Divisi')['Total_Harga'].sum().reset_index()
                st.dataframe(rekap, use_container_width=True, hide_index=True, 
                             column_config={"Total_Harga": st.column_config.NumberColumn(format="Rp %d")})
                
                total = rekap['Total_Harga'].sum()
                st.metric("Total Biaya Fisik", f"Rp {total:,.0f}")
            else:
                st.warning("Belum ada data RAB.")

    # === TAB 2: RAB PROYEK ===
    with tabs[1]:
        st.header("Input RAB")
        
        # --- Form Tambah Item ---
        with st.container():
            st.markdown("#### ➕ Tambah Pekerjaan")
            col_a, col_b, col_c = st.columns([3, 1, 1])
            
            # Ambil data unik dari Analisa
            df_ref = st.session_state['df_analysis'][['Kode_Analisa', 'Uraian_Pekerjaan']].drop_duplicates()
            options = df_ref.set_index('Kode_Analisa')['Uraian_Pekerjaan'].to_dict()
            
            with col_a:
                sel_code = st.selectbox("Pilih Pekerjaan (Dari Database)", options=list(options.keys()), 
                                        format_func=lambda x: f"{x} - {options[x]}")
            with col_b:
                vol_input = st.number_input("Volume", min_value=0.0, value=1.0)
            with col_c:
                st.write("")
                if st.button("Tambahkan"):
                    uraian = options[sel_code]
                    last_div = "UMUM"
                    if not st.session_state['df_rab'].empty:
                        last_div = st.session_state['df_rab'].iloc[-1]['Divisi']
                    
                    new_row = {
                        'No': len(st.session_state['df_rab']) + 1,
                        'Divisi': last_div,
                        'Uraian_Pekerjaan': uraian,
                        'Kode_Analisa_Ref': sel_code,
                        'Satuan_Pek': 'sat',
                        'Volume': vol_input,
                        'Harga_Satuan_Jadi': 0,
                        'Total_Harga': 0,
                        'Durasi_Minggu': 1, 'Minggu_Mulai': 1
                    }
                    st.session_state['df_rab'] = pd.concat([st.session_state['df_rab'], pd.DataFrame([new_row])], ignore_index=True)
                    calculate_system()
                    st.rerun()

        # --- Editor Tabel ---
        edited_rab = st.data_editor(
            st.session_state['df_rab'],
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Kode_Analisa_Ref": st.column_config.TextColumn(disabled=True),
                "Uraian_Pekerjaan": st.column_config.TextColumn(disabled=True),
                "Harga_Satuan_Jadi": st.column_config.NumberColumn(format="Rp %d", disabled=True),
                "Total_Harga": st.column_config.NumberColumn(format="Rp %d", disabled=True)
            }
        )
        if not edited_rab.equals(st.session_state['df_rab']):
            st.session_state['df_rab'] = edited_rab
            calculate_system()
            st.rerun()

    # === TAB 3: DATABASE AHSP (FITUR BARU) ===
    with tabs[2]:
        st.header("📚 Database Harga & Analisa")
        st.markdown("""
        **Cara Penggunaan:**
        1. Upload file `data_rab.xlsx` Anda di sini.
        2. Sistem akan membaca sheet yang berisi daftar harga.
        3. Daftar tersebut otomatis masuk ke pilihan di Tab RAB.
        """)
        
        uploaded_master = st.file_uploader("Upload File Master Excel (RAB/AHSP)", type=['xlsx'])
        if uploaded_master:
            if st.button("🚀 Proses & Masukkan ke Database"):
                process_uploaded_master(uploaded_master)
        
        st.divider()
        st.subheader("Preview Database Saat Ini")
        st.dataframe(st.session_state['df_analysis'], use_container_width=True)

    # === TAB LAINNYA (Analisa, Harga, Kurva S) ===
    with tabs[3]:
        st.write("Detail perhitungan analisa (ReadOnly)")
        st.dataframe(st.session_state['df_analysis_detailed'], use_container_width=True)
    
    with tabs[4]:
        st.write("Daftar Harga Dasar Material/Upah")
        st.dataframe(st.session_state['df_prices'], use_container_width=True)
        
    with tabs[5]:
        st.header("Kurva S")
        df_chart, df_data = generate_s_curve_data()
        if df_data is not None:
            c = alt.Chart(df_data).mark_line(point=True).encode(
                x='Minggu_Int', y='Rencana_Kumulatif', tooltip=['Minggu', 'Rencana_Kumulatif']
            )
            st.altair_chart(c, use_container_width=True)

if __name__ == "__main__":
    main()

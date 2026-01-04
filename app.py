import streamlit as st
import pandas as pd
import io
import altair as alt
from thefuzz import process  # Library untuk pencocokan teks pintar

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="SmartRAB Pro - Estimator System",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CSS CUSTOM (Agar Tampilan Mirip Aplikasi Pro) ---
st.markdown("""
<style>
    .main-header {font-size: 24px; font-weight: bold; color: #2E86C1;}
    .sub-header {font-size: 18px; font-weight: bold; color: #555;}
    .success-box {padding: 15px; background-color: #D4EDDA; border-radius: 5px; color: #155724;}
    .info-box {padding: 15px; background-color: #D1ECF1; border-radius: 5px; color: #0C5460;}
    div[data-testid="stExpander"] div[role="button"] p {
        font-size: 1.1rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. FUNGSI UTILITAS & DATA ---

@st.cache_data
def load_master_ahsp():
    """
    Mencoba memuat database AHSP dari file CSV yang diupload user sebelumnya.
    Jika tidak ada, menggunakan dummy data untuk demo.
    """
    # Coba load file CSV asli kamu (pastikan file ini ada di folder yang sama)
    csv_filename = "data_rab.xlsx - Daftar Harga Satuan Pekerjaan.csv"
    
    try:
        # Kita asumsikan format CSV kamu: NO, URAIAN PEKERJAAN, SATUAN, HARGA SATUAN
        # Sesuaikan 'header' jika baris pertama bukan header
        df = pd.read_csv(csv_filename, header=7) 
        
        # Bersihkan data (Rename kolom agar standar)
        # Mencari kolom yang relevan berdasarkan posisi atau nama mirip
        df = df.rename(columns={
            'URAIAN PEKERJAAN': 'Uraian',
            'SATUAN': 'Satuan',
            'HARGA SATUAN': 'Harga_Satuan',
            'NO': 'Kode'
        })
        
        # Filter baris kosong & konversi harga ke angka
        df = df.dropna(subset=['Uraian'])
        df['Harga_Satuan'] = pd.to_numeric(df['Harga_Satuan'], errors='coerce').fillna(0)
        
        return df[['Kode', 'Uraian', 'Satuan', 'Harga_Satuan']]
        
    except FileNotFoundError:
        st.warning(f"File '{csv_filename}' tidak ditemukan. Menggunakan Data Dummy.")
        # Data Dummy untuk demo jika file CSV tidak ada
        data = {
            'Kode': ['A.1', 'A.2', 'B.1', 'B.2', 'C.1'],
            'Uraian': [
                'Galian Tanah Biasa sedalam s.d 1 m', 
                'Urukan Pasir Bawah Pondasi', 
                'Pasangan Batu Kali 1:5', 
                'Pasangan Bata Merah 1:4',
                'Beton Mutu f\'c=19.3 Mpa (K225)'
            ],
            'Satuan': ['m3', 'm3', 'm3', 'm2', 'm3'],
            'Harga_Satuan': [75000, 250000, 1200000, 145000, 1350000]
        }
        return pd.DataFrame(data)

def generate_template_excel():
    """Membuat file Excel template untuk di-download user"""
    df_template = pd.DataFrame({
        'NO': [1, 2, 3],
        'URAIAN_PEKERJAAN': ['Galian tanah pondasi', 'Pasang bata merah', 'Cor beton kolom'],
        'VOLUME': [50.5, 120.0, 15.0],
        'LOKASI': ['Lantai 1', 'Lantai 1', 'Lantai 2']
    })
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_template.to_excel(writer, index=False, sheet_name='Input_Volume')
    return output.getvalue()

# --- 4. LOGIKA SMART MAPPING (INTI APLIKASI) ---

def smart_mapping_process(df_user, df_master):
    """
    Fungsi ini melakukan pencocokan otomatis (Fuzzy Match)
    antara input user dengan database AHSP.
    """
    mapped_data = []
    
    # List nama pekerjaan dari master untuk pencarian
    master_names = df_master['Uraian'].tolist()
    
    st.subheader("🔗 Konfirmasi Smart Linking")
    st.markdown("Aplikasi mencoba menebak item AHSP yang sesuai dengan input Anda. **Silakan koreksi jika salah.**")
    
    # Container untuk hasil
    final_rows = []

    # Iterasi setiap baris input user
    for idx, row in df_user.iterrows():
        user_desc = str(row['URAIAN_PEKERJAAN'])
        user_vol = float(row['VOLUME'])
        user_loc = str(row['LOKASI']) if 'LOKASI' in row else "-"
        
        # 1. Cari kecocokan menggunakan Fuzzy Logic
        # Mengembalikan (Match Name, Score, Index)
        best_match = process.extractOne(user_desc, master_names)
        match_name = best_match[0]
        match_score = best_match[1]
        
        # Ambil data lengkap dari master berdasarkan nama yang cocok
        master_row = df_master[df_master['Uraian'] == match_name].iloc[0]
        
        # Tampilan UI per Baris
        with st.expander(f"{idx+1}. {user_desc} ({user_loc})", expanded=(match_score < 80)):
            c1, c2, c3 = st.columns([3, 1, 4])
            
            with c1:
                st.caption("Input Anda:")
                st.info(f"**{user_desc}**\n\nVol: {user_vol}")
            
            with c2:
                st.write("\n\n")
                st.markdown("<h3 style='text-align: center;'>➡️</h3>", unsafe_allow_html=True)
            
            with c3:
                st.caption(f"Terdeteksi di Database (Akurasi: {match_score}%):")
                
                # Dropdown pencarian pintar
                # Default index adalah yang ditemukan oleh sistem
                try:
                    default_ix = master_names.index(match_name)
                except:
                    default_ix = 0
                
                selected_item = st.selectbox(
                    "Pilih Item AHSP:",
                    options=master_names,
                    index=default_ix,
                    key=f"select_{idx}"
                )
                
                # Ambil data terbaru jika user mengubah dropdown
                final_master_row = df_master[df_master['Uraian'] == selected_item].iloc[0]
                
                st.write(f"Harga: **Rp {final_master_row['Harga_Satuan']:,.0f}** / {final_master_row['Satuan']}")
        
        # Simpan hasil final untuk baris ini
        total_price = user_vol * final_master_row['Harga_Satuan']
        
        final_rows.append({
            'Lokasi': user_loc,
            'Uraian Input': user_desc,
            'Item AHSP Terpilih': final_master_row['Uraian'],
            'Kode Analisa': final_master_row['Kode'],
            'Volume': user_vol,
            'Satuan': final_master_row['Satuan'],
            'Harga Satuan': final_master_row['Harga_Satuan'],
            'Total Harga': total_price
        })
    
    return pd.DataFrame(final_rows)

# --- 5. HALAMAN UTAMA (MAIN APP) ---

def main():
    # Load Database Master
    if 'df_master' not in st.session_state:
        st.session_state['df_master'] = load_master_ahsp()
    
    if 'rab_data' not in st.session_state:
        st.session_state['rab_data'] = None

    # Sidebar
    with st.sidebar:
        st.title("🏗️ SmartRAB")
        st.write("Versi 2.0 (AI-Powered)")
        st.divider()
        st.header("Info Proyek")
        nama_proyek = st.text_input("Nama Proyek", "Renovasi Rumah Tinggal")
        lokasi_proyek = st.text_input("Lokasi", "Jakarta")
        st.divider()
        st.info("💡 Gunakan Tab 'Import Volume' untuk memasukkan data pekerjaan dari Excel.")

    # Tab Navigasi
    tab1, tab2, tab3, tab4 = st.tabs(["🏠 Home & Template", "📂 Import Volume (AI)", "💰 Hasil RAB", "📈 Dashboard"])

    # === TAB 1: HOME ===
    with tab1:
        st.markdown("<h1 class='main-header'>Selamat Datang di SmartRAB</h1>", unsafe_allow_html=True)
        st.write("""
        Aplikasi ini membantu Anda membuat Rencana Anggaran Biaya (RAB) dengan cepat.
        Fitur unggulan kami adalah **Smart Linking**: Aplikasi akan mengenali nama pekerjaan Anda
        dan otomatis mencari analisa harga satuannya.
        """)
        
        st.divider()
        st.subheader("1️⃣ Langkah Pertama: Download Template")
        st.write("Silakan download template Excel di bawah ini untuk mengisi volume pekerjaan Anda.")
        
        excel_template = generate_template_excel()
        st.download_button(
            label="📥 Download Template Volume (.xlsx)",
            data=excel_template,
            file_name="Template_Volume_SmartRAB.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.image("https://img.freepik.com/free-vector/data-extraction-concept-illustration_114360-4876.jpg", width=300)

    # === TAB 2: IMPORT VOLUME (SMART MAPPING) ===
    with tab2:
        st.header("Import & Link Data")
        
        uploaded_file = st.file_uploader("Upload File Template yang sudah diisi", type=['xlsx'])
        
        if uploaded_file:
            try:
                df_input = pd.read_excel(uploaded_file)
                st.success("File berhasil dibaca! Silakan verifikasi mapping di bawah.")
                
                # Proses Mapping
                with st.form("mapping_form"):
                    df_result = smart_mapping_process(df_input, st.session_state['df_master'])
                    
                    st.divider()
                    submit = st.form_submit_button("✅ Simpan ke RAB", type="primary")
                    
                    if submit:
                        st.session_state['rab_data'] = df_result
                        st.success("Data berhasil disimpan! Silakan pindah ke Tab 'Hasil RAB'.")
            
            except Exception as e:
                st.error(f"Terjadi kesalahan membaca file: {e}")
                st.write("Pastikan format kolom Excel sesuai template (URAIAN_PEKERJAAN, VOLUME).")

    # === TAB 3: HASIL RAB ===
    with tab3:
        st.header("Rincian Anggaran Biaya (RAB)")
        
        if st.session_state['rab_data'] is not None:
            df_rab = st.session_state['rab_data']
            
            # Grouping berdasarkan Lokasi (Lantai 1, Lantai 2, dst)
            grouped = df_rab.groupby('Lokasi')
            
            grand_total = 0
            
            for lokasi, group_df in grouped:
                with st.expander(f"📍 LOKASI: {lokasi}", expanded=True):
                    # Tampilkan Tabel
                    display_df = group_df[['Item AHSP Terpilih', 'Volume', 'Satuan', 'Harga Satuan', 'Total Harga']]
                    
                    # Formatting kolom
                    st.dataframe(
                        display_df.style.format({
                            'Harga Satuan': 'Rp {:,.0f}',
                            'Total Harga': 'Rp {:,.0f}',
                            'Volume': '{:.2f}'
                        }),
                        use_container_width=True
                    )
                    
                    subtotal = group_df['Total Harga'].sum()
                    st.markdown(f"**Subtotal {lokasi}: Rp {subtotal:,.0f}**")
                    grand_total += subtotal
            
            st.divider()
            # Total Keseluruhan
            st.markdown(f"""
            <div class='success-box' style='text-align: right;'>
                <h2>GRAND TOTAL: Rp {grand_total:,.0f}</h2>
            </div>
            """, unsafe_allow_html=True)
            
            # Export to Excel
            output_rab = io.BytesIO()
            with pd.ExcelWriter(output_rab, engine='xlsxwriter') as writer:
                df_rab.to_excel(writer, index=False, sheet_name='RAB_Final')
            
            st.download_button(
                "📥 Export RAB ke Excel",
                data=output_rab.getvalue(),
                file_name=f"RAB_{nama_proyek}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        else:
            st.info("Belum ada data RAB. Silakan lakukan Import di Tab sebelumnya.")

    # === TAB 4: DASHBOARD & KURVA ===
    with tab4:
        st.header("Dashboard Analisa")
        
        if st.session_state['rab_data'] is not None:
            df_chart = st.session_state['rab_data']
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Komposisi Biaya per Lokasi")
                chart_loc = alt.Chart(df_chart).mark_arc().encode(
                    theta='sum(Total Harga)',
                    color='Lokasi',
                    tooltip=['Lokasi', 'sum(Total Harga)']
                )
                st.altair_chart(chart_loc, use_container_width=True)
            
            with col2:
                st.subheader("Top 5 Pekerjaan Termahal")
                top_items = df_chart.nlargest(5, 'Total Harga')
                chart_bar = alt.Chart(top_items).mark_bar().encode(
                    x='Total Harga',
                    y=alt.Y('Item AHSP Terpilih', sort='-x'),
                    tooltip=['Item AHSP Terpilih', 'Total Harga']
                )
                st.altair_chart(chart_bar, use_container_width=True)
                
        else:
            st.info("Data belum tersedia untuk dashboard.")

if __name__ == "__main__":
    main()

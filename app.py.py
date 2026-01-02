import streamlit as st
import pandas as pd
import os

# --- 1. KONFIGURASI TAMPILAN ---
st.set_page_config(page_title="Pro RAB Manager", layout="wide", page_icon="🏗️")

# CSS Kustom biar tombol dan tabel lebih cantik
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px; text-align: center;}
    .big-font {font-size:24px !important; font-weight: bold;}
    div.stButton > button:first-child {background-color: #0099ff; color: white; width: 100%; border-radius: 8px;}
    div.stButton > button:hover {background-color: #007acc; border-color: #007acc;}
</style>
""", unsafe_allow_html=True)

# --- 2. FUNGSI & DATA (BACKEND) ---
FILE_EXCEL = "data_rab.xlsx"

@st.cache_data
def load_data():
    if not os.path.exists(FILE_EXCEL): return None
    try:
        return pd.read_excel(FILE_EXCEL, sheet_name=None, header=None)
    except: return None

# Inisialisasi Keranjang Belanja (Session State)
if 'keranjang_rab' not in st.session_state:
    st.session_state['keranjang_rab'] = []

# Load Data Excel
data_excel = load_data()

# --- 3. JUDUL & HEADER ---
st.title("🏗️ Aplikasi RAB Bangunan")
st.caption("Mudah, Cepat, dan Akurat | Sumber Data: Standar AHSP 2025")

if data_excel is None:
    st.error("⚠️ File 'data_rab.xlsx' tidak ditemukan! Silakan upload file Excel ke GitHub.")
    st.stop()

# Deteksi Sheet Upah
sheet_upah = next((s for s in data_excel.keys() if "upah" in s.lower() or "harga" in s.lower()), None)
kamus_harga = {}
if sheet_upah:
    df_u = data_excel[sheet_upah]
    for i, r in df_u.iterrows():
        try:
            if isinstance(r[4], (int, float)): kamus_harga[str(r[2]).strip()] = float(r[4])
        except: continue

# --- 4. MENU UTAMA (TABS) ---
tab1, tab2, tab3 = st.tabs(["➕ INPUT PEKERJAAN", "📋 LIHAT RAB SAYA", "📦 CEK HARGA DASAR"])

# === TAB 1: INPUT PEKERJAAN (KERANJANG) ===
with tab1:
    col_kiri, col_kanan = st.columns([1, 2])
    
    with col_kiri:
        st.subheader("1. Pilih Pekerjaan")
        # Filter Sheet
        daftar_kat = [s for s in data_excel.keys() if s != sheet_upah and "rekap" not in s.lower()]
        pilih_kat = st.selectbox("Kategori (Sheet):", daftar_kat)
        
        # Cari Item dalam Sheet
        df_kerja = data_excel[pilih_kat]
        list_pek = []
        for idx, row in df_kerja.iterrows():
            try:
                kode, uraian = str(row[2]), str(row[3])
                if "." in kode and len(uraian) > 3 and "Analisa" not in uraian:
                    list_pek.append({"idx": idx, "nama": f"{kode} - {uraian}"})
            except: continue
            
        pilih_item = st.selectbox("Item Pekerjaan:", list_pek, format_func=lambda x: x['nama'])
        
        st.subheader("2. Masukkan Volume")
        vol_input = st.number_input("Volume (m/m2/m3/bh):", min_value=0.0, value=1.0, step=0.1)
        
        # Hitung Harga Satuan (Hidden logic)
        total_hs = 0
        detail_komponen = []
        if pilih_item:
            start = pilih_item['idx'] + 1
            for i in range(start, len(df_kerja)):
                row = df_kerja.iloc[i]
                if str(row[2]).replace('.','').isdigit() and len(str(row[2])) < 15: break # Stop di header baru
                try:
                    nama, sat, koef = str(row[3]), str(row[4]), row[5]
                    if isinstance(koef, (int, float)) and koef > 0:
                        hrg = kamus_harga.get(nama, float(row[6]) if isinstance(row[6], (int, float)) else 0)
                        sub = koef * hrg
                        total_hs += sub
                        detail_komponen.append([nama, koef, sat, hrg, sub])
                except: continue

        st.info(f"Harga Satuan: **Rp {total_hs:,.0f}**")
        
        # TOMBOL EKSEKUSI
        st.markdown("---")
        if st.button("✅ TAMBAH KE RAB"):
            if total_hs > 0:
                item_baru = {
                    "Kategori": pilih_kat,
                    "Uraian": pilih_item['nama'],
                    "Volume": vol_input,
                    "H.Satuan": total_hs,
                    "Total": total_hs * vol_input
                }
                st.session_state['keranjang_rab'].append(item_baru)
                st.success("Berhasil ditambahkan ke daftar RAB!")
            else:
                st.warning("Item ini tidak memiliki harga (Rp 0). Cek data Excel.")

    with col_kanan:
        st.subheader("🔍 Preview Analisa")
        if detail_komponen:
            df_det = pd.DataFrame(detail_komponen, columns=["Bahan/Upah", "Koef", "Sat", "H.Dasar", "Jumlah"])
            st.dataframe(df_det.style.format({"H.Dasar":"{:,.0f}", "Jumlah":"{:,.0f}"}), use_container_width=True, height=400)
            
            # Kartu Total Preview
            st.markdown(f"""
            <div style="background-color:#d1e7dd; padding:15px; border-radius:10px; border: 1px solid #0f5132;">
                <h3 style="color:#0f5132; margin:0;">Estimasi Biaya Item Ini:</h3>
                <h1 style="color:#0f5132; margin:0;">Rp {(total_hs * vol_input):,.0f}</h1>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Pilih item pekerjaan di sebelah kiri untuk melihat rincian.")

# === TAB 2: LIHAT RAB SAYA (KERANJANG) ===
with tab2:
    st.header("📋 Rekapitulasi Rencana Anggaran Biaya")
    
    if len(st.session_state['keranjang_rab']) > 0:
        df_rab = pd.DataFrame(st.session_state['keranjang_rab'])
        
        # Tampilkan Tabel RAB
        st.dataframe(
            df_rab.style.format({"Volume": "{:,.2f}", "H.Satuan": "Rp {:,.0f}", "Total": "Rp {:,.0f}"}),
            use_container_width=True
        )
        
        # TOTAL GRAND
        grand_total = df_rab['Total'].sum()
        st.markdown("---")
        c1, c2 = st.columns([3, 1])
        with c2:
            st.markdown(f"""
            <div style="text-align:right;">
                <small>Total Proyek:</small><br>
                <span style="font-size:32px; font-weight:bold; color:#0099ff;">Rp {grand_total:,.0f}</span>
            </div>
            """, unsafe_allow_html=True)
        
        # Tombol Aksi
        st.markdown("---")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🗑️ Hapus Semua Data (Reset)"):
                st.session_state['keranjang_rab'] = []
                st.rerun()
        with col_btn2:
            # Download CSV
            csv = df_rab.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Laporan (Excel/CSV)", csv, "Laporan_RAB.csv", "text/csv")
            
    else:
        st.empty()
        st.warning("Belum ada item pekerjaan yang ditambahkan. Silakan input di Tab 'Input Pekerjaan'.")

# === TAB 3: CEK HARGA DASAR ===
with tab3:
    st.header("📦 Database Harga Satuan Dasar")
    cari = st.text_input("Cari nama bahan/upah (misal: Semen, Tukang)...")
    
    if sheet_upah:
        df_display = data_excel[sheet_upah].iloc[:, [2, 3, 4]]
        df_display.columns = ["Uraian", "Satuan", "Harga"]
        
        if cari:
            df_display = df_display[df_display['Uraian'].astype(str).str.contains(cari, case=False, na=False)]
            
        st.dataframe(df_display.style.format({"Harga": "Rp {:,.0f}"}), use_container_width=True)
    else:
        st.error("Sheet Upah tidak ditemukan.")

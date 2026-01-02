import streamlit as st
import pandas as pd
import os

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Aplikasi RAB Pro", layout="wide")
st.title("🏗️ Sistem Informasi RAB & Analisa Harga")
st.caption("Developed by SmartStudio | Data Source: data_rab.xlsx")
st.markdown("---")

# Nama file Excel yang sudah berhasil dideteksi
FILE_EXCEL = "data_rab.xlsx"

# --- FUNGSI LOAD DATA (CACHE) ---
@st.cache_data
def load_data():
    """Membaca seluruh sheet dari Excel"""
    if not os.path.exists(FILE_EXCEL):
        return None
    try:
        # Baca semua sheet sekaligus
        return pd.read_excel(FILE_EXCEL, sheet_name=None, header=None)
    except Exception as e:
        return str(e)

# --- LOAD DATA ---
data_excel = load_data()

# Cek Error Loading
if data_excel is None:
    st.error(f"❌ File '{FILE_EXCEL}' tidak ditemukan di server.")
    st.stop()
elif isinstance(data_excel, str): # Kalau balikan berupa pesan error
    st.error(f"❌ Terjadi kesalahan membaca Excel: {data_excel}")
    st.info("Pastikan file tidak dikunci password dan formatnya benar (.xlsx).")
    st.stop()

# --- 1. PROSES MASTER HARGA (AUTO DETECT) ---
# Mencari sheet yang mengandung kata "upah" atau "harga"
sheet_upah_name = None
for nama in data_excel.keys():
    if "upah" in nama.lower() or "harga" in nama.lower():
        sheet_upah_name = nama
        break

kamus_harga = {}
if sheet_upah_name:
    df_upah = data_excel[sheet_upah_name]
    # Scanning data upah (Asumsi kolom C=Nama, E=Harga)
    for index, row in df_upah.iterrows():
        try:
            nama_item = str(row.iloc[2]).strip()
            harga_item = row.iloc[4]
            if isinstance(harga_item, (int, float)) and harga_item > 0:
                kamus_harga[nama_item] = float(harga_item)
        except:
            continue
    st.sidebar.success(f"✅ Database Harga: {len(kamus_harga)} item terdeteksi.")
else:
    st.sidebar.error("⚠️ Sheet 'Upah Bahan' tidak ditemukan otomatis.")

# --- 2. MENU SIDEBAR (DAFTAR ANALISA) ---
# Ambil semua sheet KECUALI sheet upah & rekap
daftar_sheet = [s for s in data_excel.keys() 
                if s != sheet_upah_name 
                and "rekap" not in s.lower()
                and "daftar" not in s.lower()]

pilih_kategori = st.sidebar.selectbox("📂 Pilih Kategori Pekerjaan:", daftar_sheet)

# --- 3. LOGIKA HITUNGAN (MAIN APP) ---
if pilih_kategori:
    st.header(f"Analisa: {pilih_kategori}")
    
    df_kerja = data_excel[pilih_kategori]
    
    # Cari daftar sub-pekerjaan dalam sheet tersebut
    list_pekerjaan = []
    for idx, row in df_kerja.iterrows():
        try:
            kode = str(row.iloc[2])
            uraian = str(row.iloc[3])
            # Logic: Kode mengandung titik (misal 2.2.1) dan uraian cukup panjang
            if "." in kode and len(uraian) > 3 and "Analisa" not in uraian:
                list_pekerjaan.append({"baris": idx, "nama": f"{kode} - {uraian}"})
        except:
            continue

    if not list_pekerjaan:
        st.warning("⚠️ Tidak ditemukan format analisa standar di sheet ini.")
        with st.expander("Lihat Data Mentah"):
            st.dataframe(df_kerja)
    else:
        # Dropdown Pilih Item
        pilih_item = st.selectbox("👉 Pilih Item Pekerjaan:", list_pekerjaan, format_func=lambda x: x['nama'])
        
        # Input Volume
        col1, col2, col3 = st.columns([1, 2, 2])
        with col1:
            vol = st.number_input("Masukkan Volume:", min_value=0.0, value=1.0, step=0.1)
        
        st.subheader("Rincian Perhitungan Biaya")
        
        # --- PROSES EKSTRAKSI KOMPONEN ---
        start_row = pilih_item['baris'] + 1
        rincian = []
        total_ahsp = 0
        
        for i in range(start_row, len(df_kerja)):
            row = df_kerja.iloc[i]
            
            # Stop jika ketemu header pekerjaan berikutnya
            kode_cek = str(row.iloc[2])
            if "." in kode_cek and len(kode_cek) < 15 and kode_cek[0].isdigit():
                break
                
            try:
                nama_bahan = str(row.iloc[3])
                satuan = str(row.iloc[4])
                koef = row.iloc[5]
                
                # Cek baris valid (ada koefisien angka)
                if isinstance(koef, (int, float)) and koef > 0:
                    
                    # Logika Cari Harga
                    harga_satuan = 0
                    sumber = "Manual"
                    
                    # 1. Cek di Master Harga
                    if nama_bahan in kamus_harga:
                        harga_satuan = kamus_harga[nama_bahan]
                        sumber = "✅ Master Data"
                    # 2. Cek di Sheet Lokal (Backup)
                    else:
                        try:
                            harga_temp = float(row.iloc[6])
                            if harga_temp > 0:
                                harga_satuan = harga_temp
                                sumber = "⚠️ Bawaan Sheet"
                        except:
                            pass
                    
                    subtotal = koef * harga_satuan
                    total_ahsp += subtotal
                    
                    rincian.append({
                        "Komponen": nama_bahan,
                        "Koefisien": koef,
                        "Satuan": satuan,
                        "Harga Satuan": harga_satuan,
                        "Total": subtotal,
                        "Sumber": sumber
                    })
            except:
                continue
        
        # --- TAMPILKAN HASIL ---
        if rincian:
            df_hasil = pd.DataFrame(rincian)
            
            st.dataframe(
                df_hasil.style.format({
                    "Koefisien": "{:.4f}",
                    "Harga Satuan": "Rp {:,.0f}",
                    "Total": "Rp {:,.0f}"
                }),
                use_container_width=True
            )
            
            st.divider()
            
            # KARTU HASIL
            c1, c2 = st.columns(2)
            c1.metric("Harga Satuan (per m/m2/m3)", f"Rp {total_ahsp:,.0f}")
            c2.metric(f"TOTAL RAB (Volume: {vol})", f"Rp {total_ahsp * vol:,.0f}")
            
        else:
            st.info("Item ini tidak memiliki rincian koefisien.")

# Footer
st.sidebar.markdown("---")
st.sidebar.info("💡 **Tips:** Untuk update harga, edit file 'data_rab.xlsx' di komputer lalu upload ulang ke GitHub.")

import streamlit as st
import pandas as pd
import os

# --- JUDUL APLIKASI ---
st.set_page_config(page_title="Aplikasi RAB Excel", layout="wide")
st.title("🏗️ Aplikasi RAB Otomatis")
st.markdown("---")

# Nama file excel yang kakak siapkan tadi
FILE_EXCEL = "data_rab.xlsx"

# --- FUNGSI BACA DATA ---
@st.cache_data
def baca_semua_sheet():
    """Membaca file excel dan semua isinya"""
    if not os.path.exists(FILE_EXCEL):
        return None
    try:
        # Baca semua sheet tanpa header (header=None) biar kita atur sendiri
        return pd.read_excel(FILE_EXCEL, sheet_name=None, header=None)
    except Exception as e:
        st.error(f"Error: {e}")
        return None

# --- LOAD DATA ---
data_excel = baca_semua_sheet()

# Cek apakah file ada
if data_excel is None:
    st.error(f"❌ File '{FILE_EXCEL}' tidak ditemukan di folder ini!")
    st.info("👉 Pastikan nama file excelnya sudah diganti jadi: data_rab.xlsx")
    st.stop()

# --- PROSES HARGA (Cari Sheet Upah) ---
# Kita cari sheet yang namanya ada kata "Upah" atau "Harga"
sheet_harga = None
for nama_sheet in data_excel.keys():
    if "upah" in nama_sheet.lower():
        sheet_harga = nama_sheet
        break

kamus_harga = {}
if sheet_harga:
    df_upah = data_excel[sheet_harga]
    # Kita loop barisnya untuk ambil Nama (Kolom C/Idx 2) dan Harga (Kolom E/Idx 4)
    # Sesuaikan index ini dengan Excel kakak
    for index, row in df_upah.iterrows():
        try:
            nama_item = str(row.iloc[2]).strip()
            harga_item = row.iloc[4]
            # Pastikan harganya berupa angka
            if isinstance(harga_item, (int, float)) and harga_item > 0:
                kamus_harga[nama_item] = float(harga_item)
        except:
            continue
    st.sidebar.success(f"✅ Master Harga Terload: {len(kamus_harga)} item")
else:
    st.sidebar.warning("⚠️ Sheet 'Upah Bahan' tidak ditemukan otomatis.")

# --- MENU PILIH PEKERJAAN ---
# Ambil semua nama sheet KECUALI sheet upah & rekap
daftar_menu = [s for s in data_excel.keys() if s != sheet_harga and "rekap" not in s.lower()]
pilih_kategori = st.sidebar.selectbox("📂 Pilih Kategori (Sheet):", daftar_menu)

# --- TAMPILAN UTAMA ---
if pilih_kategori:
    st.header(f"Analisa: {pilih_kategori}")
    
    df_kerja = data_excel[pilih_kategori]
    
    # Cari daftar pekerjaan di dalam sheet itu
    # Logic: Cari baris yang kolom C (idx 2) isinya kode (misal 2.2.1)
    list_pekerjaan = []
    
    for idx, row in df_kerja.iterrows():
        try:
            kode = str(row.iloc[2])
            uraian = str(row.iloc[3])
            # Cek kalau kode mengandung titik (contoh: 2.2.1) dan uraiannya panjang
            if "." in kode and len(uraian) > 5 and "Analisa" not in uraian:
                list_pekerjaan.append({"baris": idx, "tampil": f"{kode} - {uraian}"})
        except:
            continue

    if len(list_pekerjaan) == 0:
        st.warning("Tidak ditemukan item pekerjaan di sheet ini. Coba sheet lain.")
        # Tampilkan data mentah buat ngecek
        st.dataframe(df_kerja.head(10)) 
    else:
        pilih_item = st.selectbox("Pilih Item Pekerjaan:", list_pekerjaan, format_func=lambda x: x['tampil'])
        
        # Input Volume
        col1, col2 = st.columns([1, 2])
        vol = col1.number_input("Masukkan Volume:", min_value=0.0, value=1.0, step=0.1)
        
        st.subheader("Rincian Biaya")
        
        # --- HITUNG DETAIL ---
        # Mulai scan dari baris header pekerjaan ke bawah
        start_row = pilih_item['baris'] + 1
        rincian_biaya = []
        total_ahsp = 0
        
        for i in range(start_row, len(df_kerja)):
            row = df_kerja.iloc[i]
            
            # Berhenti kalau ketemu kode pekerjaan baru (berarti item ini sudah selesai)
            kode_cek = str(row.iloc[2])
            if "." in kode_cek and len(kode_cek) < 10 and kode_cek[0].isdigit():
                break
                
            try:
                nama_bahan = str(row.iloc[3])
                satuan = str(row.iloc[4])
                koef = row.iloc[5] # Kolom F biasanya koefisien
                
                # Cek apakah koefisiennya angka valid
                if isinstance(koef, (int, float)) and koef > 0:
                    
                    # CARI HARGA
                    harga_satuan = 0
                    sumber = "-"
                    
                    # 1. Cek di Master Harga (Sheet Upah)
                    if nama_bahan in kamus_harga:
                        harga_satuan = kamus_harga[nama_bahan]
                        sumber = "Master Data"
                    # 2. Kalau tidak ada, ambil harga di sheet itu sendiri (Kolom G/Idx 6)
                    else:
                        try:
                            harga_temp = float(row.iloc[6])
                            if harga_temp > 0:
                                harga_satuan = harga_temp
                                sumber = "Sheet Lokal"
                        except:
                            pass
                    
                    total_sub = koef * harga_satuan
                    total_ahsp += total_sub
                    
                    rincian_biaya.append({
                        "Uraian": nama_bahan,
                        "Koefisien": koef,
                        "Satuan": satuan,
                        "Harga Satuan": harga_satuan,
                        "Total Harga": total_sub,
                        "Sumber": sumber
                    })
            except:
                continue
        
        # TAMPILKAN TABEL HASIL
        if rincian_biaya:
            df_hasil = pd.DataFrame(rincian_biaya)
            st.dataframe(df_hasil.style.format({
                "Koefisien": "{:.4f}",
                "Harga Satuan": "Rp {:,.0f}",
                "Total Harga": "Rp {:,.0f}"
            }), use_container_width=True)
            
            st.divider()
            
            # TOTAL BESAR
            c1, c2 = st.columns(2)
            c1.metric("Harga Satuan Pekerjaan", f"Rp {total_ahsp:,.0f}")
            c2.metric(f"TOTAL BIAYA (Vol: {vol})", f"Rp {total_ahsp * vol:,.0f}")
        else:
            st.info("Tidak ada rincian bahan/upah ditemukan untuk item ini.")
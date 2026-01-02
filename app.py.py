import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Cek System", layout="wide")
st.title("🕵️‍♂️ Mode Detektif: Cek File Server")

# 1. CEK FILE APA SAJA YANG ADA DI SERVER
st.write("### 1. Daftar File di Folder Ini:")
files = os.listdir('.')
st.code(files)

# 2. CEK APAKAH ADA FILE EXCEL
target_file = "data_rab.xlsx"
if target_file in files:
    st.success(f"✅ File '{target_file}' DITEMUKAN!")
    
    # 3. COBA BACA ISINYA
    try:
        df = pd.read_excel(target_file, sheet_name=None)
        st.success("✅ File Excel BISA DIBACA!")
        st.write(f"Jumlah Sheet: {len(df.keys())}")
        st.write("Nama Sheet:", list(df.keys()))
    except Exception as e:
        st.error(f"❌ Gagal membaca Excel. Pesan Error: {e}")
        st.info("💡 TIPS: Pastikan di requirements.txt sudah ada tulisan: openpyxl")
else:
    st.error(f"❌ File '{target_file}' TIDAK DITEMUKAN.")
    st.warning("👉 Cek nama file di atas. Apakah huruf besar/kecilnya beda?")

st.write("---")
st.caption("Jika ini sudah benar, baru kita paste kode aplikasi asli.")

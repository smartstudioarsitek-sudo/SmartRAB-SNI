import streamlit as st
import pandas as pd
import io
import xlsxwriter
import altair as alt
import streamlit.components.v1 as components
import re

# ==========================================
# 0. HELPER FUNCTIONS & CONFIG
# ==========================================
st.set_page_config(page_title="SmartRAB-SNI Pro", layout="wide", page_icon="🏗️")

def clean_currency(val):
    """Membersihkan format uang (Rp 1.000.000 -> 1000000)"""
    if pd.isna(val) or val == '': return 0.0
    s = str(val).replace('Rp', '').replace('.', '').replace(' ', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def normalize_text(text):
    """Normalisasi teks untuk pencocokan (lowercase, no simbol)"""
    if not isinstance(text, str): return ""
    return text.lower().strip().replace('"', '').replace("'", "")

def detect_division(filename):
    """Mendeteksi Divisi berdasarkan Nama File"""
    fn = filename.lower()
    if 'persiapan' in fn or 'bongkaran' in fn: return "Divisi 1: Umum & Persiapan"
    if 'tanah' in fn or 'galian' in fn or 'timbunan' in fn: return "Divisi 2: Pekerjaan Tanah"
    if 'pondasi' in fn or 'beton' in fn or 'baja' in fn or 'struktur' in fn: return "Divisi 3: Struktur"
    if 'dinding' in fn or 'plesteran' in fn or 'lantai' in fn: return "Divisi 4: Arsitektur"
    if 'pintu' in fn or 'jendela' in fn or 'kaca' in fn or 'kusen' in fn: return "Divisi 5: Kusen & Pintu"
    if 'atap' in fn or 'plafon' in fn: return "Divisi 6: Atap & Plafon"
    if 'cat' in fn or 'pengecatan' in fn: return "Divisi 7: Pengecatan"
    if 'sanitair' in fn or 'air' in fn or 'pipa' in fn or 'drainase' in fn: return "Divisi 8: MEP & Sanitasi"
    if 'listrik' in fn or 'elektrikal' in fn: return "Divisi 9: Elektrikal"
    return "Divisi 10: Lain-lain"

# ==========================================
# 1. INTELLECTUAL PARSER ENGINE
# ==========================================
def process_bulk_files(uploaded_files):
    """
    Memproses banyak file sekaligus (Upah Bahan + Analisa).
    """
    msg_container = []
    
    # 1. Cari File Master Harga dulu (Prioritas)
    master_file = None
    analysis_files = []
    
    for f in uploaded_files:
        if "upah" in f.name.lower() or "harga" in f.name.lower():
            master_file = f
        else:
            analysis_files.append(f)
            
    # 2. Proses Master Harga
    if master_file:
        try:
            # Reset pointer file
            master_file.seek(0)
            df_price = pd.read_csv(master_file)
            
            # Mapping Kolom Fleksibel
            col_map = {c: c.lower() for c in df_price.columns}
            price_data = []
            
            for _, row in df_price.iterrows():
                # Cari kolom yang relevan
                # Logic: Kolom pertama biasanya kode, kolom harga angka, uraian teks
                vals = row.values
                try:
                    # Heuristic parsing (Menebak posisi kolom)
                    p_kode = str(vals[0]) if len(vals) > 0 else ""
                    p_uraian = str(vals[1]) if len(vals) > 1 else ""
                    p_satuan = str(vals[2]) if len(vals) > 2 else "Unit"
                    p_harga = vals[3] if len(vals) > 3 else 0
                    
                    if pd.notna(p_uraian) and "No" not in str(p_kode):
                        price_data.append({
                            'Kode': p_kode,
                            'Komponen': p_uraian,
                            'Satuan': p_satuan,
                            'Harga_Dasar': clean_currency(p_harga),
                            'Kategori': 'Upah' if 'L.' in str(p_kode) else ('Alat' if 'E.' in str(p_kode) else 'Material')
                        })
                except: continue
                
            if price_data:
                df_new_prices = pd.DataFrame(price_data)
                # Gabungkan dengan yang lama (Upsert)
                st.session_state['df_prices'] = pd.concat([st.session_state['df_prices'], df_new_prices]).drop_duplicates(subset=['Komponen'], keep='last')
                msg_container.append(f"✅ Master Harga Updated: {len(price_data)} items")
        except Exception as e:
            msg_container.append(f"❌ Error Master Harga: {str(e)}")

    # 3. Proses Analisa (Batch)
    new_analyses = []
    
    for f in analysis_files:
        try:
            f.seek(0)
            # Deteksi Divisi dari Nama File
            detected_div = detect_division(f.name)
            
            # Baca CSV (Skip header metadata SNI yang biasanya di baris atas)
            # Kita baca raw dan parse manual line-by-line agar aman
            content = f.getvalue().decode('utf-8', errors='ignore').splitlines()
            
            curr_code, curr_desc = None, None
            
            for line in content:
                parts = line.split(',') # Simple CSV split
                if len(parts) < 3: continue
                
                c1 = parts[0].strip().replace('"', '')
                c2 = parts[1].strip().replace('"', '')
                c3 = parts[2].strip().replace('"', '')
                
                # Deteksi Header (Kode A.x.x)
                if re.match(r'^A\.|^[\d]+\.', c1) and len(c2) > 5:
                    curr_code = c1
                    curr_desc = c2
                    continue
                elif re.match(r'^A\.|^[\d]+\.', c2) and len(c3) > 5:
                    curr_code = c2
                    curr_desc = c3
                    continue
                
                # Deteksi Komponen (Ada Koefisien)
                # Mencari angka desimal di kolom ke-4 atau 5
                coef = 0
                comp_name = ""
                
                # Coba cari koefisien di bagian belakang
                for i in range(3, len(parts)):
                    try:
                        val = parts[i].replace('"', '').strip()
                        if re.match(r'^\d+(\.\d+)?$', val):
                            coef = float(val)
                            # Jika ketemu koefisien, ambil nama di kolom sebelumnya
                            if coef > 0:
                                # Nama komponen biasanya di c2 atau c3
                                comp_name = c2 if len(c2) > 2 else c3
                                break
                    except: pass
                
                if curr_code and coef > 0 and len(comp_name) > 2:
                    new_analyses.append({
                        'Kode_Analisa': curr_code,
                        'Uraian_Pekerjaan': curr_desc, # Deskripsi dari Header
                        'Komponen': comp_name,
                        'Koefisien': coef,
                        'Divisi_Ref': detected_div # Metadata tambahan
                    })
                    
        except Exception as e:
            msg_container.append(f"⚠️ Skip {f.name}: {str(e)}")

    if new_analyses:
        df_new = pd.DataFrame(new_analyses)
        st.session_state['df_analysis'] = pd.concat([st.session_state['df_analysis'], df_new], ignore_index=True)
        # Hapus duplikat
        st.session_state['df_analysis'] = st.session_state['df_analysis'].drop_duplicates(subset=['Kode_Analisa', 'Komponen'])
        msg_container.append(f"✅ Analisa Updated: {len(new_analyses)} baris komponen baru.")
        
    return msg_container

# ==========================================
# 2. LOGIC SISTEM (LINKING HARGA & RAB)
# ==========================================
def calculate_system():
    df_p = st.session_state['df_prices'].copy()
    df_a = st.session_state['df_analysis'].copy()
    df_r = st.session_state['df_rab'].copy()
    overhead_factor = 1 + (st.session_state.get('global_overhead', 15.0) / 100)

    # 1. Normalisasi Key untuk Matching
    df_p['Key'] = df_p['Komponen'].apply(normalize_text)
    df_a['Key_Raw'] = df_a['Komponen'].apply(normalize_text)
    
    # 2. Kamus Harga (Lookup Dictionary)
    price_dict = dict(zip(df_p['Key'], df_p['Harga_Dasar']))
    satuan_dict = dict(zip(df_p['Key'], df_p['Satuan']))
    kategori_dict = dict(zip(df_p['Key'], df_p['Kategori']))
    
    # 3. Fungsi Pencarian Harga (Smart Match)
    def find_best_price(key_search):
        # A. Exact Match
        if key_search in price_dict:
            return price_dict[key_search], satuan_dict.get(key_search, '-'), kategori_dict.get(key_search, 'Material')
        # B. Partial Match (Misal: "Semen" -> "Semen Portland")
        for k_db, price in price_dict.items():
            if (key_search in k_db and len(key_search)>3) or (k_db in key_search and len(k_db)>3):
                return price, satuan_dict.get(k_db, '-'), kategori_dict.get(k_db, 'Material')
        return 0.0, '-', 'Material'

    # 4. Terapkan Harga ke Analisa
    results = df_a['Key_Raw'].apply(find_best_price)
    df_a['Harga_Dasar'] = [res[0] for res in results]
    df_a['Satuan'] = [res[1] for res in results]
    df_a['Kategori'] = [res[2] for res in results]
    df_a['Subtotal'] = df_a['Koefisien'] * df_a['Harga_Dasar']
    
    st.session_state['df_analysis_detailed'] = df_a

    # 5. Hitung Harga Satuan Jadi (Harsat)
    unit_prices = df_a.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices['Harga_Kalkulasi'] = unit_prices['Subtotal'] * overhead_factor 
    
    # 6. Update RAB
    df_r['Kode_Analisa_Ref'] = df_r['Kode_Analisa_Ref'].astype(str).str.strip()
    unit_prices['Kode_Analisa'] = unit_prices['Kode_Analisa'].astype(str).str.strip()
    
    df_r_temp = pd.merge(df_r, unit_prices[['Kode_Analisa', 'Harga_Kalkulasi']], left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
    df_r['Harga_Satuan_Jadi'] = df_r_temp['Harga_Kalkulasi'].fillna(0)
    df_r['Total_Harga'] = df_r['Volume'] * df_r['Harga_Satuan_Jadi']
    st.session_state['df_rab'] = df_r

    # 7. Rekap Material
    mat_bk = pd.merge(df_r[['Kode_Analisa_Ref', 'Volume']], df_a[['Kode_Analisa', 'Komponen', 'Satuan', 'Koefisien', 'Harga_Dasar']], left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
    mat_bk['Total_Kebutuhan'] = mat_bk['Volume'] * mat_bk['Koefisien']
    mat_bk['Total_Biaya'] = mat_bk['Total_Kebutuhan'] * mat_bk['Harga_Dasar']
    st.session_state['df_material_rekap'] = mat_bk.groupby(['Komponen', 'Satuan']).agg({'Total_Kebutuhan': 'sum', 'Total_Biaya': 'sum'}).reset_index()

# ==========================================
# 3. UI SIDEBAR & NAVIGASI
# ==========================================
def render_sidebar():
    st.sidebar.title("🔧 Data Center")
    
    # --- FITUR BARU: BULK UPLOAD ---
    with st.sidebar.expander("📥 1. Upload Database (Massal)", expanded=True):
        st.caption("Upload semua file CSV (Upah Bahan + Divisi) sekaligus di sini.")
        uploaded_files = st.file_uploader("Drop file di sini:", accept_multiple_files=True, type=['csv'], key="bulk_upload")
        
        if uploaded_files:
            if st.button("🚀 Proses Semua File"):
                with st.spinner("Sedang membaca & memetakan data..."):
                    logs = process_bulk_files(uploaded_files)
                    calculate_system()
                st.success("Selesai!")
                for log in logs:
                    st.caption(log)
    
    st.sidebar.markdown("---")
    
    # --- KATALOG VIEW ---
    if 'df_analysis_detailed' not in st.session_state: calculate_system()
    df_det = st.session_state['df_analysis_detailed']
    
    if not df_det.empty:
        # Grouping untuk Sidebar Dropdown
        unique_items = df_det.drop_duplicates(subset=['Kode_Analisa'])
        
        # Filter Divisi (Menggunakan Divisi_Ref jika ada hasil deteksi file, jika tidak pakai logic kode)
        if 'Divisi_Ref' not in unique_items.columns:
            unique_items['Divisi_Ref'] = "Umum"
            
        div_list = sorted(unique_items['Divisi_Ref'].unique())
        sel_div = st.sidebar.selectbox("Filter Divisi:", ["Semua"] + list(div_list))
        
        if sel_div != "Semua":
            unique_items = unique_items[unique_items['Divisi_Ref'] == sel_div]
            
        # Pilih Item
        unique_items['Label'] = unique_items['Uraian_Pekerjaan']
        sel_item_label = st.sidebar.selectbox("Pilih Item:", unique_items['Label'].unique())
        
        # Detail Item
        if sel_item_label:
            item_row = unique_items[unique_items['Label'] == sel_item_label].iloc[0]
            ov_factor = 1 + (st.session_state.get('global_overhead', 15)/100)
            
            # Hitung Harga Realtime
            est_price = df_det[df_det['Kode_Analisa'] == item_row['Kode_Analisa']]['Subtotal'].sum() * ov_factor
            
            st.sidebar.info(f"Kode: {item_row['Kode_Analisa']}\nHarga: Rp {est_price:,.0f}")
            
            c1, c2 = st.sidebar.columns(2)
            vol = c1.number_input("Vol", 1.0, step=1.0)
            dur = c2.number_input("Mg", 1, step=1)
            
            if st.sidebar.button("➕ Add to RAB"):
                new_row = {
                    'No': len(st.session_state.df_rab)+1,
                    'Divisi': sel_div if sel_div != "Semua" else "Pekerjaan Umum",
                    'Uraian_Pekerjaan': sel_item_label,
                    'Kode_Analisa_Ref': item_row['Kode_Analisa'],
                    'Satuan_Pek': 'Unit',
                    'Volume': vol,
                    'Harga_Satuan_Jadi': 0, 'Total_Harga': 0,
                    'Durasi_Minggu': dur, 'Minggu_Mulai': 1
                }
                st.session_state.df_rab = pd.concat([st.session_state.df_rab, pd.DataFrame([new_row])], ignore_index=True)
                calculate_system()
                st.rerun()

# ==========================================
# 4. INISIALISASI DATA (SEED)
# ==========================================
def initialize_data():
    defaults = {'global_overhead': 15.0, 'project_name': 'Proyek Percontohan', 'project_loc': 'Jakarta', 'project_year': '2025'}
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

    # Init DataFrame
    if 'df_prices' not in st.session_state:
        # Default minimal agar tidak error sebelum upload
        st.session_state['df_prices'] = pd.DataFrame(columns=['Kode', 'Komponen', 'Satuan', 'Harga_Dasar', 'Kategori'])
    
    if 'df_analysis' not in st.session_state:
        # Default minimal
        st.session_state['df_analysis'] = pd.DataFrame(columns=['Kode_Analisa', 'Uraian_Pekerjaan', 'Komponen', 'Koefisien', 'Divisi_Ref'])

    if 'df_rab' not in st.session_state:
        st.session_state['df_rab'] = pd.DataFrame(columns=[
            'No', 'Divisi', 'Uraian_Pekerjaan', 'Kode_Analisa_Ref', 'Satuan_Pek', 
            'Volume', 'Harga_Satuan_Jadi', 'Total_Harga', 'Durasi_Minggu', 'Minggu_Mulai'
        ])

    # Cek & Fix Struktur Table
    cols_rab = ['Durasi_Minggu', 'Minggu_Mulai', 'Kode_Analisa_Ref']
    for c in cols_rab:
        if c not in st.session_state['df_rab'].columns:
            st.session_state['df_rab'][c] = 1 if c != 'Kode_Analisa_Ref' else ''

    calculate_system()

# ==========================================
# 5. HALAMAN UTAMA (UI TABS)
# ==========================================
def render_sni_html(kode, uraian, df_part, ov):
    """Render tabel analisa cantik"""
    html = f"<div style='border:1px solid #ccc; padding:15px; border-radius:5px; background:white;'>"
    html += f"<h4 style='margin:0;'>{kode} - {uraian}</h4><hr>"
    html += f"<table style='width:100%; border-collapse:collapse; font-size:14px;'>"
    total = 0
    for idx, row in df_part.iterrows():
        sub = row['Subtotal']
        total += sub
        html += f"<tr style='border-bottom:1px solid #eee;'><td>{row['Komponen']}</td><td width='15%'>{row['Koefisien']} {row['Satuan']}</td><td width='25%' style='text-align:right;'>Rp {sub:,.0f}</td></tr>"
    html += f"<tr style='font-weight:bold; background:#f9f9f9;'><td>TOTAL HARGA DASAR</td><td></td><td style='text-align:right;'>Rp {total:,.0f}</td></tr>"
    html += f"<tr style='font-weight:bold; color:blue;'><td>HARGA JADI (+{ov}%)</td><td></td><td style='text-align:right;'>Rp {total*(1+ov/100):,.0f}</td></tr></table></div>"
    return html

def to_excel(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as w: df.to_excel(w, index=False)
    return out.getvalue()

def main():
    initialize_data()
    render_sidebar()
    
    st.title("🏗️ SmartRAB-SNI (Enterprise Edition)")
    
    tabs = st.tabs(["📊 REKAP", "📝 RAB", "🔍 ANALISA DETIL", "💰 HARGA DASAR", "🧱 MATERIAL", "📈 KURVA-S"])

    # --- TAB 1: REKAP ---
    with tabs[0]:
        st.header("Rekapitulasi Biaya")
        
        c1, c2 = st.columns([3, 1])
        with c2:
            st.markdown("### ⚙️ Setting")
            ov = st.number_input("Overhead (%)", 0.0, 50.0, st.session_state['global_overhead'])
            if ov != st.session_state['global_overhead']:
                st.session_state['global_overhead'] = ov
                calculate_system()
                st.rerun()
                
            if st.button("🗑️ Hapus Semua Data (Reset)"):
                st.session_state.clear()
                st.rerun()

        with c1:
            df = st.session_state['df_rab']
            if not df.empty:
                # Group by Divisi
                rekap = df.groupby('Divisi')['Total_Harga'].sum().reset_index()
                st.dataframe(rekap, use_container_width=True, hide_index=True, column_config={"Total_Harga": st.column_config.NumberColumn(format="Rp %d")})
                
                gt = rekap['Total_Harga'].sum()
                ppn = gt * 0.11
                st.success(f"### TOTAL FISIK: Rp {gt:,.0f}")
                st.info(f"### GRAND TOTAL (+PPN 11%): Rp {gt+ppn:,.0f}")
            else:
                st.warning("Data RAB masih kosong.")

    # --- TAB 2: RAB ---
    with tabs[1]:
        st.header("Rincian RAB")
        
        # Input Tengah (Manual)
        with st.expander("➕ Tambah Manual"):
            df_det = st.session_state.get('df_analysis_detailed', pd.DataFrame())
            if not df_det.empty:
                codes = df_det['Kode_Analisa'].unique()
                c_sel = st.selectbox("Pilih Kode:", codes)
                c_div = st.text_input("Divisi:", "Pekerjaan Umum")
                c_vol = st.number_input("Volume:", 1.0)
                
                if st.button("Simpan Item"):
                    desc = df_det[df_det['Kode_Analisa']==c_sel].iloc[0]['Uraian_Pekerjaan']
                    new_row = {
                        'No': len(st.session_state.df_rab)+1,
                        'Divisi': c_div,
                        'Uraian_Pekerjaan': desc,
                        'Kode_Analisa_Ref': c_sel,
                        'Satuan_Pek': 'Unit',
                        'Volume': c_vol,
                        'Harga_Satuan_Jadi': 0, 'Total_Harga': 0, 'Durasi_Minggu': 1, 'Minggu_Mulai': 1
                    }
                    st.session_state.df_rab = pd.concat([st.session_state.df_rab, pd.DataFrame([new_row])], ignore_index=True)
                    calculate_system()
                    st.rerun()

        # Tabel RAB Editor
        df_rab = st.session_state['df_rab']
        edited = st.data_editor(df_rab, use_container_width=True, num_rows="dynamic", column_config={
            "Total_Harga": st.column_config.NumberColumn(format="Rp %d", disabled=True),
            "Harga_Satuan_Jadi": st.column_config.NumberColumn(format="Rp %d", disabled=True)
        })
        
        if not edited.equals(df_rab):
            st.session_state['df_rab'] = edited
            calculate_system()
            st.rerun()

    # --- TAB 3: ANALISA ---
    with tabs[2]:
        st.header("Bedah Analisa")
        df_det = st.session_state['df_analysis_detailed']
        
        if not df_det.empty:
            all_codes = df_det['Kode_Analisa'].unique()
            sel_code = st.selectbox("Cari Analisa:", all_codes)
            
            if sel_code:
                part = df_det[df_det['Kode_Analisa'] == sel_code]
                desc = part.iloc[0]['Uraian_Pekerjaan']
                st.markdown(render_sni_html(sel_code, desc, part, st.session_state['global_overhead']), unsafe_allow_html=True)
        else:
            st.info("Belum ada data analisa. Silakan Upload File di Sidebar.")

    # --- TAB 4: HARGA DASAR ---
    with tabs[3]:
        st.header("Master Harga (Upah & Bahan)")
        df_p = st.session_state['df_prices']
        edited_p = st.data_editor(df_p, use_container_width=True, num_rows="dynamic", key='editor_harga')
        
        if not edited_p.equals(df_p):
            st.session_state['df_prices'] = edited_p
            calculate_system()
            st.rerun()

    # --- TAB 5: MATERIAL ---
    with tabs[4]:
        st.header("Rekap Kebutuhan Sumber Daya")
        if 'df_material_rekap' in st.session_state:
            st.dataframe(st.session_state['df_material_rekap'], use_container_width=True)

    # --- TAB 6: KURVA S ---
    with tabs[5]:
        st.header("Jadwal & Kurva S")
        df = st.session_state['df_rab'].copy()
        if df['Total_Harga'].sum() > 0:
            df['Bobot'] = (df['Total_Harga'] / df['Total_Harga'].sum()) * 100
            max_week = int(df.apply(lambda x: x['Minggu_Mulai'] + x['Durasi_Minggu'] - 1, axis=1).max())
            if max_week < 1: max_week = 1
            
            curve_data = []
            cum = 0
            for w in range(1, max_week + 2):
                val = 0
                for _, r in df.iterrows():
                    if r['Minggu_Mulai'] <= w < (r['Minggu_Mulai'] + r['Durasi_Minggu']):
                        val += (r['Bobot'] / r['Durasi_Minggu'])
                cum = min(cum + val, 100)
                curve_data.append({'Minggu': w, 'Progress': cum})
            
            df_curve = pd.DataFrame(curve_data)
            chart = alt.Chart(df_curve).mark_line(point=True).encode(x='Minggu', y='Progress', tooltip=['Minggu', 'Progress']).interactive()
            st.altair_chart(chart, use_container_width=True)
        else:
            st.warning("RAB masih kosong.")

if __name__ == "__main__":
    main()

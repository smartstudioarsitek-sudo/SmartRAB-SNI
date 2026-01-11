import streamlit as st
import pandas as pd
import io
import xlsxwriter
import altair as alt
import streamlit.components.v1 as components
import re

# ==========================================
# 0. HELPER FUNCTIONS (LOGIC BARU)
# ==========================================
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

# ==========================================
# 1. MODUL DATABASE AHSP (ADAPTIVE)
# ==========================================
def get_catalog_view():
    """Mengambil view gabungan untuk Sidebar."""
    if 'df_analysis_detailed' not in st.session_state:
        calculate_system()
        
    df_det = st.session_state['df_analysis_detailed']
    ov_factor = 1 + (st.session_state.get('global_overhead', 15.0) / 100)
    catalog = []
    
    if not df_det.empty:
        unique_codes = df_det['Kode_Analisa'].unique()
        for code in unique_codes:
            slice_data = df_det[df_det['Kode_Analisa'] == code]
            if slice_data.empty: continue
            
            first_row = slice_data.iloc[0]
            desc = first_row['Uraian_Pekerjaan']
            total_dasar = slice_data['Subtotal'].sum()
            final_price = total_dasar * ov_factor
            
            # --- Auto Kategorisasi Divisi (Berdasarkan Kode Awal) ---
            code_str = str(code)
            category = "Umum"
            if code_str.startswith("A.1"): category = "Divisi 1: Persiapan"
            elif code_str.startswith("A.2"): category = "Divisi 2: Tanah"
            elif code_str.startswith("A.3"): category = "Divisi 3: Struktur"
            elif code_str.startswith("A.4"): category = "Divisi 4: Arsitektur (Dinding/Lantai)"
            elif code_str.startswith("A.5"): category = "Divisi 5: Kusen, Pintu & Jendela"
            elif code_str.startswith("A.6"): category = "Divisi 6: Atap & Plafon"
            elif code_str.startswith("A.7"): category = "Divisi 7: Pengecatan"
            elif code_str.startswith("A.8"): category = "Divisi 8: Sanitasi (Plumbing)"
            elif code_str.startswith("A.9"): category = "Divisi 9: Elektrikal"
            elif code_str.startswith("A.10"): category = "Divisi 10: Besi & Lain-lain"

            catalog.append({
                "Category": category,
                "Item": desc,
                "Unit": "Unit", 
                "Price": final_price,
                "Kode_Ref": code
            })
            
    return pd.DataFrame(catalog)

# ==========================================
# 2. SIDEBAR UI
# ==========================================
def render_ahsp_selector():
    st.sidebar.markdown("---")
    st.sidebar.subheader("📚 Database AHSP (Lengkap)")
    
    df_ahsp = get_catalog_view()
    if df_ahsp.empty:
        st.sidebar.warning("Database kosong. Reset Data di Tab 1.")
        return

    # Sort kategori agar urut Divisi 1 - 10
    kategori_list = sorted(df_ahsp['Category'].unique())
    selected_category = st.sidebar.selectbox("Pilih Divisi Pekerjaan", kategori_list)
    
    filtered_items = df_ahsp[df_ahsp['Category'] == selected_category]
    filtered_items['Label_View'] = filtered_items['Item']
    
    selected_item_name = st.sidebar.selectbox("Pilih Item Pekerjaan", filtered_items['Label_View'].unique())
    
    # Ambil detail
    item_row = filtered_items[filtered_items['Label_View'] == selected_item_name].iloc[0]
    st.sidebar.info(f"Estimasi: Rp {item_row['Price']:,.0f}")
    
    col_vol, col_dur = st.sidebar.columns(2)
    with col_vol:
        vol_input = st.number_input("Volume", min_value=1.0, value=10.0, step=1.0, key='vol_ahsp')
    with col_dur:
        dur_input = st.number_input("Durasi (Mg)", min_value=1, value=1, key='dur_ahsp')
    start_input = st.sidebar.number_input("Minggu Ke-", min_value=1, value=1, key='start_ahsp')

    if st.sidebar.button("➕ Masukkan ke RAB"):
        try:
            selected_code = item_row['Kode_Ref']
            new_rab = {
                'No': len(st.session_state.df_rab) + 1,
                'Divisi': selected_category,
                'Uraian_Pekerjaan': selected_item_name,
                'Kode_Analisa_Ref': selected_code,
                'Satuan_Pek': item_row['Unit'],
                'Volume': vol_input,
                'Harga_Satuan_Jadi': 0, 
                'Total_Harga': 0,     
                'Bobot': 0,
                'Durasi_Minggu': dur_input,
                'Minggu_Mulai': start_input
            }
            st.session_state.df_rab = pd.concat([st.session_state.df_rab, pd.DataFrame([new_rab])], ignore_index=True)
            st.sidebar.success(f"Sukses! {selected_item_name} ditambahkan.")
            calculate_system()
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Terjadi kesalahan: {e}")

# ==========================================
# CONFIG & INIT
# ==========================================
st.set_page_config(page_title="SmartRAB-SNI", layout="wide")

def initialize_data():
    # Default Config
    defaults = {'global_overhead': 15.0, 'project_name': '-', 'project_loc': '-', 'project_year': '2025'}
    for key, val in defaults.items():
        if key not in st.session_state: st.session_state[key] = val

    # --- 1. DATA HARGA DASAR (LENGKAP 10 DIVISI) ---
    if 'df_prices' not in st.session_state:
        data_prices = {
            'Kode': [
                # Material Alam
                'M.01', 'M.02', 'M.03', 'M.04', 
                # Material Arsitek (Lantai/Dinding)
                'M.05', 'M.06', 'M.07', 'M.08',
                # Material Atap & Plafon
                'M.09', 'M.10', 'M.11',
                # Material Kusen & Pintu
                'M.12', 'M.13', 
                # Material MEP (Pipa & Kabel)
                'M.14', 'M.15', 'M.16', 'M.17',
                # Upah & Alat
                'L.01', 'L.02', 'L.03', 'L.04', 'E.01'
            ],
            'Komponen': [
                'Semen Portland', 'Pasir Beton', 'Batu Kali', 'Paku', 
                'Bata Merah', 'Keramik 40x40', 'Semen Nat', 'Cat Tembok',
                'Baja Ringan C75', 'Hollow Galvalum', 'Gypsum Board 9mm',
                'Kusen Aluminium 4 Inch', 'Kaca Polos 5mm',
                'Pipa PVC 1/2 Inch', 'Kloset Duduk', 'Kabel NYM 3x2.5', 'Saklar Tunggal',
                'Pekerja', 'Tukang Batu', 'Kepala Tukang', 'Mandor', 'Sewa Molen'
            ],
            'Satuan': [
                'kg', 'kg', 'm3', 'kg', 
                'bh', 'm2', 'kg', 'kg',
                'btg', 'btg', 'lbr',
                'm', 'm2',
                'btg', 'unit', 'm', 'bh',
                'OH', 'OH', 'OH', 'OH', 'Jam'
            ],
            'Harga_Dasar': [
                1300, 300, 286500, 15000, 
                800, 65000, 12000, 25000,
                110000, 45000, 65000,
                120000, 150000,
                35000, 1500000, 12000, 25000,
                100000, 145000, 175000, 200000, 85000
            ],
            'Kategori': ['Material'] * 17 + ['Upah'] * 4 + ['Alat']
        }
        st.session_state['df_prices'] = pd.DataFrame(data_prices)

    # --- 2. DATA ANALISA (LENGKAP 10 DIVISI) ---
    if 'df_analysis' not in st.session_state:
        # Kita bangun list analisa manual agar lengkap 10 Divisi
        # Structure: Code, Desc, Component, Coef
        
        # Div 1: Persiapan
        a_div1 = [
            ('A.1.1', 'Pagar Sementara Seng', 'Semen Portland', 2.5),
            ('A.1.1', 'Pagar Sementara Seng', 'Pekerja', 0.4),
            ('A.1.2', 'Pembersihan Lahan', 'Pekerja', 0.1),
        ]
        # Div 2: Tanah
        a_div2 = [
            ('A.2.1', 'Galian Tanah Biasa', 'Pekerja', 0.75),
            ('A.2.1', 'Galian Tanah Biasa', 'Mandor', 0.025),
        ]
        # Div 3: Struktur
        a_div3 = [
            ('A.3.1', 'Pondasi Batu Kali 1:4', 'Batu Kali', 1.2),
            ('A.3.1', 'Pondasi Batu Kali 1:4', 'Semen Portland', 163.0),
            ('A.3.1', 'Pondasi Batu Kali 1:4', 'Pekerja', 1.5),
            ('A.3.2', 'Beton Cor Manual', 'Semen Portland', 350),
            ('A.3.2', 'Beton Cor Manual', 'Pasir Beton', 800),
            ('A.3.2', 'Beton Cor Manual', 'Sewa Molen', 0.2),
        ]
        # Div 4: Arsitektur (Dinding & Lantai)
        a_div4 = [
            ('A.4.1', 'Pasang Dinding Bata Merah', 'Bata Merah', 70),
            ('A.4.1', 'Pasang Dinding Bata Merah', 'Semen Portland', 12),
            ('A.4.1', 'Pasang Dinding Bata Merah', 'Pekerja', 0.3),
            ('A.4.2', 'Pasang Lantai Keramik 40x40', 'Keramik 40x40', 1.05),
            ('A.4.2', 'Pasang Lantai Keramik 40x40', 'Semen Nat', 1.5),
            ('A.4.2', 'Pasang Lantai Keramik 40x40', 'Tukang Batu', 0.25),
        ]
        # Div 5: Kusen Pintu Jendela
        a_div5 = [
            ('A.5.1', 'Pasang Kusen Aluminium', 'Kusen Aluminium 4 Inch', 1.1),
            ('A.5.1', 'Pasang Kusen Aluminium', 'Tukang Batu', 0.1),
            ('A.5.2', 'Pasang Kaca Jendela', 'Kaca Polos 5mm', 1.05),
        ]
        # Div 6: Atap & Plafon
        a_div6 = [
            ('A.6.1', 'Rangka Atap Baja Ringan', 'Baja Ringan C75', 1.5),
            ('A.6.1', 'Rangka Atap Baja Ringan', 'Pekerja', 0.2),
            ('A.6.2', 'Pasang Plafon Gypsum', 'Gypsum Board 9mm', 0.35),
            ('A.6.2', 'Pasang Plafon Gypsum', 'Hollow Galvalum', 4.0),
        ]
        # Div 7: Pengecatan
        a_div7 = [
            ('A.7.1', 'Pengecatan Tembok Baru', 'Cat Tembok', 0.25),
            ('A.7.1', 'Pengecatan Tembok Baru', 'Pekerja', 0.05),
        ]
        # Div 8: Sanitasi (Plumbing)
        a_div8 = [
            ('A.8.1', 'Pasang Kloset Duduk', 'Kloset Duduk', 1.0),
            ('A.8.1', 'Pasang Kloset Duduk', 'Tukang Batu', 1.5),
            ('A.8.2', 'Instalasi Pipa Air Bersih', 'Pipa PVC 1/2 Inch', 1.2),
        ]
        # Div 9: Elektrikal
        a_div9 = [
            ('A.9.1', 'Titik Lampu & Kabel', 'Kabel NYM 3x2.5', 12.0),
            ('A.9.1', 'Titik Lampu & Kabel', 'Tukang Batu', 0.5), # Asumsi tukang listrik
            ('A.9.2', 'Pasang Saklar', 'Saklar Tunggal', 1.0),
        ]
        # Div 10: Besi & Lainnya
        a_div10 = [
            ('A.10.1', 'Pagar Besi BRC', 'Pekerja', 0.5),
            ('A.10.1', 'Pagar Besi BRC', 'Semen Portland', 5.0), # Angkur
        ]

        all_data = a_div1 + a_div2 + a_div3 + a_div4 + a_div5 + a_div6 + a_div7 + a_div8 + a_div9 + a_div10
        
        df_new = pd.DataFrame(all_data, columns=['Kode_Analisa', 'Uraian_Pekerjaan', 'Komponen', 'Koefisien'])
        st.session_state['df_analysis'] = df_new

    # --- 3. DATA RAB (SAFE INIT) ---
    if 'df_rab' not in st.session_state:
        data_rab = {
            'No': [1],
            'Divisi': ['PEKERJAAN STRUKTUR BAWAH'], 
            'Uraian_Pekerjaan': ['Pondasi Batu Kali 1:4'],
            'Kode_Analisa_Ref': ['A.3.1'],
            'Satuan_Pek': ['m3'],
            'Volume': [50.0],
            'Harga_Satuan_Jadi': [0.0],
            'Total_Harga': [0.0],
            'Durasi_Minggu': [2],
            'Minggu_Mulai': [1]
        }
        st.session_state['df_rab'] = pd.DataFrame(data_rab)
    
    # --- ANTI-CRASH CHECK ---
    # Memastikan kolom penting selalu ada (Recovery Mode)
    req_cols = ['Kode_Analisa_Ref', 'Durasi_Minggu', 'Minggu_Mulai']
    for col in req_cols:
        if col not in st.session_state['df_rab'].columns:
            st.session_state['df_rab'][col] = '' if col == 'Kode_Analisa_Ref' else 1
            
    calculate_system()

# --- 3. LOGIC UTAMA ---
def calculate_system():
    df_p = st.session_state['df_prices'].copy()
    df_a = st.session_state['df_analysis'].copy()
    df_r = st.session_state['df_rab'].copy()
    overhead_factor = 1 + (st.session_state.get('global_overhead', 15.0) / 100)

    # Normalisasi Key
    df_p['Key'] = df_p['Komponen'].apply(normalize_text)
    df_a['Key_Raw'] = df_a['Komponen'].apply(normalize_text)
    
    # Lookup Dictionary
    price_dict = dict(zip(df_p['Key'], df_p['Harga_Dasar']))
    satuan_dict = dict(zip(df_p['Key'], df_p['Satuan']))
    kategori_dict = dict(zip(df_p['Key'], df_p['Kategori']))
    
    def find_best_price(key_search):
        if key_search in price_dict:
            return price_dict[key_search], satuan_dict.get(key_search, '-'), kategori_dict.get(key_search, 'Material')
        for k_db, price in price_dict.items():
            if key_search in k_db or k_db in key_search:
                return price, satuan_dict.get(k_db, '-'), kategori_dict.get(k_db, 'Material')
        return 0.0, '-', 'Material'

    results = df_a['Key_Raw'].apply(find_best_price)
    df_a['Harga_Dasar'] = [res[0] for res in results]
    df_a['Satuan'] = [res[1] for res in results]
    df_a['Kategori'] = [res[2] for res in results]
    df_a['Subtotal'] = df_a['Koefisien'] * df_a['Harga_Dasar']
    
    st.session_state['df_analysis_detailed'] = df_a

    # Harsat Calculation
    unit_prices = df_a.groupby('Kode_Analisa')['Subtotal'].sum().reset_index()
    unit_prices['Harga_Kalkulasi'] = unit_prices['Subtotal'] * overhead_factor 
    
    # Link to RAB
    df_r['Kode_Analisa_Ref'] = df_r['Kode_Analisa_Ref'].astype(str).str.strip()
    unit_prices['Kode_Analisa'] = unit_prices['Kode_Analisa'].astype(str).str.strip()
    
    df_r_temp = pd.merge(df_r, unit_prices[['Kode_Analisa', 'Harga_Kalkulasi']], left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left')
    df_r['Harga_Satuan_Jadi'] = df_r_temp['Harga_Kalkulasi'].fillna(0)
    df_r['Total_Harga'] = df_r['Volume'] * df_r['Harga_Satuan_Jadi']
    st.session_state['df_rab'] = df_r

    # Rekap Material
    mat_bk = pd.merge(
        df_r[['Kode_Analisa_Ref', 'Volume']], 
        df_a[['Kode_Analisa', 'Komponen', 'Satuan', 'Koefisien', 'Harga_Dasar']], 
        left_on='Kode_Analisa_Ref', right_on='Kode_Analisa', how='left'
    )
    mat_bk['Total_Kebutuhan'] = mat_bk['Volume'] * mat_bk['Koefisien']
    mat_bk['Total_Biaya'] = mat_bk['Total_Kebutuhan'] * mat_bk['Harga_Dasar']
    
    rekap_final = mat_bk.groupby(['Komponen', 'Satuan']).agg({'Total_Kebutuhan': 'sum', 'Total_Biaya': 'sum'}).reset_index()
    st.session_state['df_material_rekap'] = rekap_final

# --- 4. S-CURVE & HELPERS ---
def generate_s_curve_data():
    df = st.session_state['df_rab'].copy()
    if df['Total_Harga'].sum() == 0: return None, None
    df['Bobot_Pct'] = (df['Total_Harga'] / df['Total_Harga'].sum()) * 100
    
    max_week = int(df.apply(lambda x: x['Minggu_Mulai'] + x['Durasi_Minggu'] - 1, axis=1).max())
    if pd.isna(max_week) or max_week < 1: max_week = 1
    
    cumulative_list = []
    cum_prog = 0
    for w in range(1, max_week + 2):
        weight = 0
        for _, row in df.iterrows():
            if row['Minggu_Mulai'] <= w <= (row['Minggu_Mulai'] + row['Durasi_Minggu'] - 1):
                weight += (row['Bobot_Pct'] / row['Durasi_Minggu'])
        cum_prog = min(cum_prog + weight, 100)
        cumulative_list.append({'Minggu': f"M{w}", 'Minggu_Int': w, 'Rencana_Kumulatif': cum_prog})
    return df, pd.DataFrame(cumulative_list)

def render_print_style():
    st.markdown("""<style>@media print { [data-testid="stHeader"], [data-testid="stSidebar"], footer { display: none !important; } }</style>""", unsafe_allow_html=True)

def render_print_button():
    components.html("""<div style="text-align: right;"><button onclick="window.parent.print()" style="padding:8px;font-weight:bold;">🖨️ Cetak / Print</button></div>""", height=60)

def to_excel(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as w: df.to_excel(w, index=False)
    return out.getvalue()

def render_sni_html(kode, uraian, df_part, ov):
    html = f"<div style='border:1px solid black; padding:10px;'><b>AHSP {kode} - {uraian}</b><br><table style='width:100%; border-collapse:collapse;'>"
    total = 0
    for idx, row in df_part.iterrows():
        sub = row['Subtotal']
        total += sub
        html += f"<tr style='border-bottom:1px solid #ddd;'><td>{row['Komponen']}</td><td>{row['Koefisien']} {row['Satuan']}</td><td style='text-align:right;'>Rp {sub:,.0f}</td></tr>"
    html += f"<tr style='font-weight:bold; background:#eee;'><td>HARGA DASAR</td><td></td><td style='text-align:right;'>Rp {total:,.0f}</td></tr>"
    html += f"<tr style='font-weight:bold;'><td>HARGA JADI (+{ov}%)</td><td></td><td style='text-align:right;'>Rp {total*(1+ov/100):,.0f}</td></tr></table></div>"
    return html

# --- 5. MAIN APP ---
def main():
    initialize_data()
    render_print_style()
    render_ahsp_selector() # Sidebar
    
    st.title("🏗️ SmartRAB-SNI (10 Divisi Lengkap)")
    
    tabs = st.tabs(["📊 REKAP", "📝 RAB", "🔍 ANALISA", "💰 HARGA", "🧱 MATERIAL", "📈 KURVA-S"])

    # TAB 1: REKAP
    with tabs[0]:
        st.header("Rekapitulasi")
        render_print_button()
        
        # Tombol Reset Database (PENTING untuk user lama agar update ke 10 Divisi)
        if st.button("🔄 Reset Database ke Default (10 Divisi)"):
            for key in ['df_prices', 'df_analysis', 'df_rab', 'df_analysis_detailed']:
                if key in st.session_state: del st.session_state[key]
            st.rerun()
            
        col_main, col_opt = st.columns([2, 1])
        with col_opt:
            st.markdown("**Pengaturan**")
            ov = st.number_input("Overhead (%)", 0.0, 50.0, st.session_state['global_overhead'], step=0.5)
            if ov != st.session_state['global_overhead']:
                st.session_state['global_overhead'] = ov
                calculate_system()
                st.rerun()
        
        with col_main:
            df_rab = st.session_state['df_rab']
            if 'Divisi' in df_rab.columns:
                rekap = df_rab.groupby('Divisi')['Total_Harga'].sum().reset_index()
                st.dataframe(rekap, use_container_width=True, hide_index=True, column_config={"Total_Harga": st.column_config.NumberColumn(format="Rp %d")})
                st.metric("TOTAL BIAYA", f"Rp {rekap['Total_Harga'].sum():,.0f}")

    # TAB 2: RAB
    with tabs[1]:
        st.header("RAB Editor")
        
        # Form Input Tengah
        st.markdown("### ➕ Input Cepat (Tengah)")
        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
        
        # Ambil list pekerjaan yang sudah di-sort per divisi
        df_det = st.session_state.get('df_analysis_detailed', pd.DataFrame())
        if not df_det.empty:
            df_det = df_det.sort_values('Kode_Analisa')
            # Buat label "Kode - Nama"
            df_det['Label'] = df_det['Kode_Analisa'] + " - " + df_det['Uraian_Pekerjaan']
            # Ambil unique
            unique_opts = df_det[['Kode_Analisa', 'Label']].drop_duplicates()
            
            with c1:
                sel_code = st.selectbox("Pilih Pekerjaan", unique_opts['Kode_Analisa'], format_func=lambda x: unique_opts[unique_opts['Kode_Analisa']==x]['Label'].iloc[0])
            with c2:
                div_input = st.text_input("Divisi", value="PEKERJAAN TAMBAHAN")
            with c3:
                vol_input = st.number_input("Vol", 1.0, step=1.0)
            with c4:
                st.write(""); st.write("")
                if st.button("Tambahkan"):
                    # Cari uraian
                    uraian = unique_opts[unique_opts['Kode_Analisa']==sel_code]['Label'].iloc[0].split(" - ", 1)[1]
                    new_row = {'No': len(st.session_state.df_rab)+1, 'Divisi': div_input, 'Uraian_Pekerjaan': uraian, 'Kode_Analisa_Ref': sel_code, 'Satuan_Pek': 'Unit', 'Volume': vol_input, 'Harga_Satuan_Jadi': 0, 'Total_Harga': 0, 'Durasi_Minggu': 1, 'Minggu_Mulai': 1}
                    st.session_state.df_rab = pd.concat([st.session_state.df_rab, pd.DataFrame([new_row])], ignore_index=True)
                    calculate_system()
                    st.rerun()

        # Tabel RAB
        edited = st.data_editor(st.session_state['df_rab'], use_container_width=True, num_rows="dynamic", column_config={"Total_Harga": st.column_config.NumberColumn(format="Rp %d", disabled=True), "Harga_Satuan_Jadi": st.column_config.NumberColumn(format="Rp %d", disabled=True)})
        if not edited.equals(st.session_state['df_rab']):
            st.session_state['df_rab'] = edited
            calculate_system()
            st.rerun()

    # TAB 3: ANALISA
    with tabs[2]:
        st.header("Detail Analisa")
        df_det = st.session_state['df_analysis_detailed']
        sel = st.selectbox("Lihat Analisa:", df_det['Kode_Analisa'].unique())
        if sel:
            sub = df_det[df_det['Kode_Analisa'] == sel]
            st.markdown(render_sni_html(sel, sub['Uraian_Pekerjaan'].iloc[0], sub, st.session_state['global_overhead']), unsafe_allow_html=True)
            
        with st.expander("Upload CSV Analisa Baru"):
            up = st.file_uploader("Upload CSV", type='csv')
            if up:
                try:
                    nd = pd.read_csv(up, header=None)
                    # Simple parser logic (Column 0=Code, 1=Desc, 2=Comp, 4=Coef)
                    parsed = []
                    curr_code, curr_desc = None, None
                    for _, r in nd.iterrows():
                        if pd.notna(r[0]) and "A." in str(r[0]): 
                            curr_code, curr_desc = r[0], r[1]
                        elif curr_code and pd.notna(r[4]):
                            parsed.append({'Kode_Analisa': curr_code, 'Uraian_Pekerjaan': curr_desc, 'Komponen': r[1], 'Koefisien': float(r[4])})
                    if parsed:
                        st.session_state['df_analysis'] = pd.concat([st.session_state['df_analysis'], pd.DataFrame(parsed)], ignore_index=True)
                        calculate_system()
                        st.success("Analisa baru ditambahkan!")
                except: st.error("Format CSV tidak sesuai")

    # TAB 4: HARGA
    with tabs[3]:
        st.header("Master Harga")
        ed_p = st.data_editor(st.session_state['df_prices'], use_container_width=True, num_rows="dynamic")
        if not ed_p.equals(st.session_state['df_prices']):
            st.session_state['df_prices'] = ed_p
            calculate_system()
            st.rerun()

    # TAB 5: MATERIAL
    with tabs[4]:
        st.header("Kebutuhan Material")
        if 'df_material_rekap' in st.session_state:
            st.dataframe(st.session_state['df_material_rekap'], use_container_width=True)

    # TAB 6: KURVA S
    with tabs[5]:
        st.header("Kurva S")
        _, curv = generate_s_curve_data()
        if curv is not None:
            c = alt.Chart(curv).mark_line(point=True).encode(x='Minggu_Int', y='Rencana_Kumulatif', tooltip=['Minggu', 'Rencana_Kumulatif']).interactive()
            st.altair_chart(c, use_container_width=True)
        else: st.info("Data RAB kosong")

if __name__ == "__main__":
    main()

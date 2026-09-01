import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
from datetime import datetime, timedelta
import os

st.set_page_config(
    page_title="Life Logger - Hábitos & Comportamento",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------------------
# DATABASE SETUP & INITIAL MIGRATION
# -------------------------------------------------------------
DB_PATH = "life_logger.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            categoria TEXT NOT NULL,
            local TEXT NOT NULL,
            amount REAL,
            tipo TEXT,
            duracao REAL,
            calorias REAL,
            mood TEXT,
            gatilho TEXT,
            nota TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # Set default location if not present
    c.execute("INSERT OR IGNORE INTO app_state (key, value) VALUES ('current_location', 'São Paulo')")
    conn.commit()
    conn.close()

def get_current_location():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM app_state WHERE key='current_location'")
    row = c.fetchone()
    conn.close()
    return row[0] if row else "São Paulo"

def set_current_location(loc):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE app_state SET value=? WHERE key='current_location'", (loc,))
    conn.commit()
    conn.close()

def log_event(categoria, amount=None, tipo=None, duracao=None, calorias=None, mood=None, gatilho=None, nota=None, local_override=None):
    loc = local_override if local_override else get_current_location()
    now_str = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO habits (timestamp, categoria, local, amount, tipo, duracao, calorias, mood, gatilho, nota)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (now_str, categoria, loc, amount, tipo, duracao, calorias, mood, gatilho, nota))
    conn.commit()
    conn.close()

def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM habits ORDER BY timestamp DESC", conn)
    conn.close()
    if not df.empty:
        df['dt'] = pd.to_datetime(df['timestamp'])
        df['hora'] = df['dt'].dt.hour
        df['dia_semana'] = df['dt'].dt.day_name().map({
            'Monday': 'Segunda', 'Tuesday': 'Terça', 'Wednesday': 'Quarta',
            'Thursday': 'Quinta', 'Friday': 'Sexta', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
        })
        def get_p(h):
            if 5 <= h < 12: return 'Manhã (05h-12h)'
            elif 12 <= h < 18: return 'Tarde (12h-18h)'
            elif 18 <= h < 23: return 'Noite (18h-23h)'
            else: return 'Madrugada (23h-05h)'
        df['turno'] = df['hora'].apply(get_p)
    return df

init_db()

# Check if database is empty, seed with initial excel if available
conn = sqlite3.connect(DB_PATH)
count = conn.cursor().execute("SELECT count(*) FROM habits").fetchone()[0]
conn.close()

if count == 0 and os.path.exists('life-logger1 .xlsx'):
    try:
        raw = pd.read_excel('life-logger1 .xlsx')
        raw['data_clean'] = raw['data'].astype(str).str.replace('T112:', 'T12:')
        raw['dt_utc'] = pd.to_datetime(raw['data_clean'])
        raw['dt_brt'] = raw['dt_utc'] - pd.Timedelta(hours=3)
        raw = raw.sort_values('dt_brt').reset_index(drop=True)
        
        # State persistence / forward fill for location
        def clean_l(l):
            l = str(l).strip()
            if l.lower() in ['sp', 'são paulo', 'sao paulo']: return 'São Paulo'
            if l.lower() in ['cpv', 'caçapava', 'cacapava']: return 'Caçapava'
            if l.lower() in ['sp-cpv', 'cpv-sp']: return 'Estrada / Posto'
            if l.lower() == 'nan' or l == '': return np.nan
            return l
        
        raw['loc_clean'] = raw['location'].apply(clean_l).ffill().fillna('São Paulo')
        
        conn = sqlite3.connect(DB_PATH)
        for _, r in raw.iterrows():
            conn.cursor().execute("""
                INSERT INTO habits (timestamp, categoria, local, amount, tipo, duracao, calorias, mood, gatilho, nota)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r['dt_brt'].strftime("%Y-%m-%d %H:%M:%S"),
                str(r['categoria']),
                str(r['loc_clean']),
                r['amount'] if pd.notnull(r['amount']) else None,
                str(r['type']) if pd.notnull(r['type']) else None,
                r['duration'] if pd.notnull(r['duration']) else None,
                r['calories'] if pd.notnull(r['calories']) else None,
                str(r['mood']) if pd.notnull(r['mood']) else None,
                None,
                str(r['nota']) if pd.notnull(r['nota']) else (str(r['description']) if pd.notnull(r['description']) else None)
            ))
        conn.commit()
        conn.close()
    except Exception as e:
        st.warning(f"Aviso ao carregar histórico inicial: {e}")

# -------------------------------------------------------------
# SIDEBAR: PERSISTENT STATE & FAST CONTROLS
# -------------------------------------------------------------
curr_loc = get_current_location()

st.sidebar.title("🧭 Estado Atual")
st.sidebar.markdown(f"**Local Ativo:** `{curr_loc}`")

loc_options = ["São Paulo", "Caçapava", "Estrada / Deslocamento", "Goiânia", "Viagem"]
new_loc = st.sidebar.selectbox("Alterar Localização:", loc_options, index=loc_options.index(curr_loc) if curr_loc in loc_options else 0)
if st.sidebar.button("Atualizar Local"):
    set_current_location(new_loc)
    st.sidebar.success(f"Local alterado para: {new_loc}")
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("⚡ Registro Rápido (1 Toque)")

col_b1, col_b2 = st.sidebar.columns(2)
with col_b1:
    if st.button("🚬 +1 Cigarro", use_container_width=True):
        log_event(categoria="Cigarro", amount=1)
        st.toast(f"Cigarro registrado em {curr_loc}!", icon="🚬")
        st.rerun()

with col_b2:
    if st.button("💧 +1 Água", use_container_width=True):
        log_event(categoria="Água", amount=1)
        st.toast("Água registrada!", icon="💧")
        st.rerun()

# -------------------------------------------------------------
# MAIN APP TABS
# -------------------------------------------------------------
tab_reg, tab_dash, tab_dados = st.tabs(["📝 Novo Registro", "📊 Análise & Dashboard", "🗄️ Dados Históricos"])

with tab_reg:
    st.header("Novo Registro Detalhado")
    st.caption("Todos os novos registros herdam automaticamente o local ativo, a menos que você mude.")
    
    with st.form("form_registro", clear_on_submit=True):
        f_cat = st.selectbox("Categoria:", ["Cigarro", "Exercício", "Bebida", "Humor", "Água", "Leitura", "Outro"])
        
        c1, c2, c3 = st.columns(3)
        with c1:
            f_amount = st.number_input("Quantidade (unidades, copos, etc.):", min_value=0.0, step=1.0, value=1.0)
        with c2:
            f_tipo = st.text_input("Tipo / Modalidade (ex: Musculação, Corrida, Vinho, Cerveja):")
        with c3:
            f_duracao = st.number_input("Duração (minutos, se aplicável):", min_value=0.0, step=5.0, value=0.0)
            
        c4, c5 = st.columns(2)
        with c4:
            f_calorias = st.number_input("Calorias estimadas (kcal):", min_value=0.0, step=10.0, value=0.0)
        with c5:
            f_gatilho = st.selectbox("Gatilho Identificado:", [
                "Nenhum / Rotina",
                "Pós-Reunião / Trabalho",
                "Ansiedade / Início de Semana",
                "Transição de Viagem / Posto",
                "Fim de Noite / Ócio / YouTube",
                "Social / Cerveja",
                "Conflito Emocional / Raiva",
                "Pausa de Estudo"
            ])
            
        f_mood = st.text_input("Estado de Humor / Sentimento (ex: Ansioso, Relaxado, Cansado):")
        f_nota = st.text_area("Nota / Detalhes Emocionais do Momento:")
        
        submit = st.form_submit_button("Salvar Registro Completo", use_container_width=True)
        if submit:
            log_event(
                categoria=f_cat,
                amount=f_amount if f_amount > 0 else None,
                tipo=f_tipo if f_tipo else None,
                duracao=f_duracao if f_duracao > 0 else None,
                calorias=f_calorias if f_calorias > 0 else None,
                mood=f_mood if f_mood else None,
                gatilho=f_gatilho if f_gatilho != "Nenhum / Rotina" else None,
                nota=f_nota if f_nota else None
            )
            st.success("Registro adicionado com sucesso!")
            st.rerun()

with tab_dash:
    st.header("Painel de Hábitos & Comportamento")
    df = load_data()
    
    if df.empty:
        st.info("Nenhum dado encontrado para análise.")
    else:
        cigs = df[df['categoria'] == 'Cigarro']
        exs = df[df['categoria'] == 'Exercício']
        
        # Metrics Row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Cigarros", f"{int(cigs['amount'].sum())} un")
        m2.metric("Sessões de Fumo", f"{len(cigs)} eventos")
        m3.metric("Sessões de Treino", f"{len(exs)} treinos")
        m4.metric("Turno Pico de Fumo", "Noite / Madrugada")
        
        st.divider()
        
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("Cigarros por Localidade (Herança Ativa)")
            cigs_loc = cigs.groupby('local')['amount'].sum().reset_index()
            fig_loc = px.bar(cigs_loc, x='local', y='amount', color='local', title="Consumo Total por Local")
            st.plotly_chart(fig_loc, use_container_width=True)
            
        with g2:
            st.subheader("Cigarros por Turno do Dia")
            cigs_turn = cigs.groupby('turno')['amount'].sum().reindex(['Manhã (05h-12h)', 'Tarde (12h-18h)', 'Noite (18h-23h)', 'Madrugada (23h-05h)']).dropna().reset_index()
            fig_turn = px.pie(cigs_turn, names='turno', values='amount', hole=0.4, title="Distribuição por Turno")
            st.plotly_chart(fig_turn, use_container_width=True)
            
        g3, g4 = st.columns(2)
        with g3:
            st.subheader("Cigarros por Dia da Semana")
            dias = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
            cigs_dias = cigs.groupby('dia_semana')['amount'].sum().reindex(dias).dropna().reset_index()
            fig_dias = px.bar(cigs_dias, x='dia_semana', y='amount', title="Volume Semanal")
            st.plotly_chart(fig_dias, use_container_width=True)
            
        with g4:
            st.subheader("Horários dos Exercícios")
            ex_turn = exs.groupby('turno')['id'].count().reset_index()
            fig_ex = px.bar(ex_turn, x='turno', y='id', labels={'id': 'Qtd Treinos'}, title="Distribuição dos Treinos por Horário")
            st.plotly_chart(fig_ex, use_container_width=True)

with tab_dados:
    st.header("Base de Dados Completa")
    df_all = load_data()
    st.dataframe(df_all, use_container_width=True)
    
    csv = df_all.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Baixar Dados em CSV",
        data=csv,
        file_name='life_logger_backup.csv',
        mime='text/csv'
    )

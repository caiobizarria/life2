import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
from datetime import datetime, timedelta
import os

st.set_page_config(
    page_title="Life Logger - Hábitos & Rotina",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------------------
# DATABASE CONFIGURATION
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
        df['data_apenas'] = df['dt'].dt.date
        df['hora'] = df['dt'].dt.hour
        df['dia_semana'] = df['dt'].dt.day_name().map({
            'Monday': 'Segunda', 'Tuesday': 'Terça', 'Wednesday': 'Quarta',
            'Thursday': 'Quinta', 'Friday': 'Sexta', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
        })
        df['semana_inicio'] = df['dt'].apply(lambda d: d.date() - timedelta(days=d.weekday()))
        df['semana_rotulo'] = df['semana_inicio'].apply(lambda d: f"Semana {d.strftime('%d/%m')}")
        
        def get_p(h):
            if 5 <= h < 12: return 'Manhã (05h-12h)'
            elif 12 <= h < 18: return 'Tarde (12h-18h)'
            elif 18 <= h < 23: return 'Noite (18h-23h)'
            else: return 'Madrugada (23h-05h)'
        df['turno'] = df['hora'].apply(get_p)
    return df

init_db()

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
        st.warning(f"Aviso ao migrar: {e}")

# -------------------------------------------------------------
# SIDEBAR: PERSISTÊNCIA & REGISTRO RÁPIDO
# -------------------------------------------------------------
curr_loc = get_current_location()

st.sidebar.title("🧭 Life Logger")
st.sidebar.markdown(f"**Local Ativo:** `{curr_loc}`")

loc_options = ["São Paulo", "Caçapava", "Estrada / Deslocamento", "Goiânia", "Viagem"]
new_loc = st.sidebar.selectbox("Alterar Localização:", loc_options, index=loc_options.index(curr_loc) if curr_loc in loc_options else 0)
if st.sidebar.button("Atualizar Local", use_container_width=True):
    set_current_location(new_loc)
    st.sidebar.success(f"Local: {new_loc}")
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("⚡ Registro Rápido (Mais Usados)")

c_col1, c_col2 = st.sidebar.columns([3, 2])
with c_col1:
    if st.button("🚬 +1 Cigarro", use_container_width=True):
        log_event(categoria="Cigarro", amount=1)
        st.toast(f"+1 Cigarro em {curr_loc}", icon="🚬")
        st.rerun()
with c_col2:
    if st.button("🚬 +2", use_container_width=True):
        log_event(categoria="Cigarro", amount=2)
        st.toast(f"+2 Cigarros em {curr_loc}", icon="🚬")
        st.rerun()

st.sidebar.caption("🏋️‍♂️ Treinos Rápidos")
col_e1, col_e2 = st.sidebar.columns(2)
with col_e1:
    if st.button("🏋️ Musculação", help="45 min - 350 kcal", use_container_width=True):
        log_event(categoria="Exercício", tipo="Musculação", duracao=45, calorias=350, amount=1)
        st.toast("Treino de Musculação registrado!", icon="💪")
        st.rerun()
with col_e2:
    if st.button("🏃 Corrida", help="5km - 45 min", use_container_width=True):
        log_event(categoria="Exercício", tipo="Corrida", duracao=45, calorias=450, amount=1, nota="5km")
        st.toast("Corrida registrada!", icon="🏃")
        st.rerun()

col_e3, col_e4 = st.sidebar.columns(2)
with col_e3:
    if st.button("🏀 Basquete", help="Parque / Quadra", use_container_width=True):
        log_event(categoria="Exercício", tipo="Basquete", duracao=45, calorias=600, amount=1)
        st.toast("Basquete registrado!", icon="🏀")
        st.rerun()
with col_e4:
    if st.button("🚴 Bike", help="Ciclismo / Estrada", use_container_width=True):
        log_event(categoria="Exercício", tipo="Ciclismo", duracao=60, calorias=500, amount=1)
        st.toast("Pedal registrado!", icon="🚴")
        st.rerun()

st.sidebar.caption("🍻 Bebidas")
col_b1, col_b2 = st.sidebar.columns(2)
with col_b1:
    if st.button("🍺 Cerveja", use_container_width=True):
        log_event(categoria="Bebida", tipo="Cerveja", amount=1)
        st.toast("+1 Cerveja registrada!", icon="🍺")
        st.rerun()
with col_b2:
    if st.button("🍷 Vinho", use_container_width=True):
        log_event(categoria="Bebida", tipo="Vinho", amount=1)
        st.toast("+1 Taça de Vinho registrada!", icon="🍷")
        st.rerun()

# -------------------------------------------------------------
# MAIN APP TABS
# -------------------------------------------------------------
tab_semana, tab_evolucao, tab_novo, tab_dados = st.tabs([
    "📅 Visão Semanal", 
    "📈 Evolução & Histórico", 
    "📝 Registro Detalhado", 
    "🗄️ Dados Brutos"
])

df = load_data()

with tab_semana:
    st.header("Acompanhamento Semanal")
    st.caption("Visão focada na sua rotina recente para tomada de decisão no dia a dia.")
    
    if df.empty:
        st.info("Nenhum dado registrado.")
    else:
        todas_semanas = sorted(df['semana_inicio'].unique(), reverse=True)
        semanas_dict = {
            s: f"Semana de {s.strftime('%d/%m/%Y')} a {(s + timedelta(days=6)).strftime('%d/%m/%Y')}"
            for s in todas_semanas
        }
        
        col_filtro, _ = st.columns([2, 2])
        with col_filtro:
            semana_sel = st.selectbox(
                "Selecione a Semana:", 
                options=todas_semanas, 
                format_func=lambda s: semanas_dict[s]
            )
            
        df_sem = df[df['semana_inicio'] == semana_sel].copy()
        
        cigs_sem = df_sem[df_sem['categoria'] == 'Cigarro']
        exs_sem = df_sem[df_sem['categoria'] == 'Exercício']
        beb_sem = df_sem[df_sem['categoria'] == 'Bebida']
        
        tot_cigarros = int(cigs_sem['amount'].sum()) if not cigs_sem.empty else 0
        tot_treinos = len(exs_sem)
        tot_tempo_treino = int(exs_sem['duracao'].sum()) if not exs_sem.empty else 0
        tot_bebidas = int(beb_sem['amount'].sum()) if not beb_sem.empty else 0
        
        semana_ant = semana_sel - timedelta(days=7)
        df_ant = df[df['semana_inicio'] == semana_ant]
        cigs_ant = int(df_ant[df_ant['categoria'] == 'Cigarro']['amount'].sum()) if not df_ant.empty else 0
        exs_ant = len(df_ant[df_ant['categoria'] == 'Exercício']) if not df_ant.empty else 0
        
        diff_cigs = tot_cigarros - cigs_ant if cigs_ant > 0 else None
        diff_exs = tot_treinos - exs_ant if exs_ant > 0 else None

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🚬 Cigarros na Semana", f"{tot_cigarros} un", delta=f"{diff_cigs:+d} vs sem. anterior" if diff_cigs is not None else None, delta_color="inverse")
        m2.metric("🏋️‍♂️ Treinos na Semana", f"{tot_treinos} sessões", delta=f"{diff_exs:+d} vs sem. anterior" if diff_exs is not None else None)
        m3.metric("⏱️ Tempo de Treino", f"{tot_tempo_treino} min")
        m4.metric("🍻 Bebidas", f"{tot_bebidas} un")
        
        st.divider()
        
        g1, g2 = st.columns(2)
        dias_ordem = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
        
        with g1:
            st.subheader("Cigarros por Dia (Nesta Semana)")
            cigs_dias = cigs_sem.groupby('dia_semana')['amount'].sum().reindex(dias_ordem, fill_value=0).reset_index()
            fig_sem_c = px.bar(
                cigs_dias, x='dia_semana', y='amount', 
                labels={'dia_semana': 'Dia', 'amount': 'Cigarros'},
                text='amount',
                color='amount',
                color_continuous_scale='Reds'
            )
            fig_sem_c.update_traces(textposition='outside')
            st.plotly_chart(fig_sem_c, use_container_width=True)
            
        with g2:
            st.subheader("Treinos por Dia (Nesta Semana)")
            exs_dias = exs_sem.groupby('dia_semana')['id'].count().reindex(dias_ordem, fill_value=0).reset_index()
            fig_sem_e = px.bar(
                exs_dias, x='dia_semana', y='id', 
                labels={'dia_semana': 'Dia', 'id': 'Treinos'},
                text='id',
                color='id',
                color_continuous_scale='Greens'
            )
            fig_sem_e.update_traces(textposition='outside')
            st.plotly_chart(fig_sem_e, use_container_width=True)
            
        st.subheader("Eventos Registrados Nesta Semana")
        cols_view = ['timestamp', 'categoria', 'local', 'tipo', 'amount', 'duracao', 'gatilho', 'mood', 'nota']
        st.dataframe(df_sem[cols_view], use_container_width=True)

with tab_evolucao:
    st.header("Evolução Semanal Comparativa")
    st.caption("Acompanhe a tendência de redução de fumo e frequência de treinos.")
    
    if not df.empty:
        sem_cigarros = df[df['categoria'] == 'Cigarro'].groupby('semana_inicio')['amount'].sum().reset_index()
        sem_cigarros.columns = ['semana', 'total_cigarros']
        
        sem_treinos = df[df['categoria'] == 'Exercício'].groupby('semana_inicio')['id'].count().reset_index()
        sem_treinos.columns = ['semana', 'total_treinos']
        
        sem_df = pd.merge(sem_cigarros, sem_treinos, on='semana', how='outer').fillna(0).sort_values('semana')
        sem_df['semana_txt'] = sem_df['semana'].apply(lambda d: d.strftime('%d/%m'))
        
        c_evo1, c_evo2 = st.columns(2)
        with c_evo1:
            fig_evo_cig = px.line(
                sem_df, x='semana_txt', y='total_cigarros', 
                markers=True, title="Total de Cigarros por Semana",
                labels={'semana_txt': 'Semana', 'total_cigarros': 'Qtd Cigarros'},
                color_discrete_sequence=['#E11D48']
            )
            fig_evo_cig.update_traces(line=dict(width=3))
            st.plotly_chart(fig_evo_cig, use_container_width=True)
            
        with c_evo2:
            fig_evo_ex = px.bar(
                sem_df, x='semana_txt', y='total_treinos', 
                title="Sessões de Exercício por Semana",
                labels={'semana_txt': 'Semana', 'total_treinos': 'Treinos'},
                color_discrete_sequence=['#10B981']
            )
            st.plotly_chart(fig_evo_ex, use_container_width=True)

with tab_novo:
    st.header("Novo Registro Detalhado")
    st.caption(f"Local herdado automaticamente: **{curr_loc}**")
    
    with st.form("form_registro", clear_on_submit=True):
        f_cat = st.selectbox("Categoria:", ["Cigarro", "Exercício", "Bebida", "Humor", "Estudo", "Leitura", "Outro"])
        
        c1, c2, c3 = st.columns(3)
        with c1:
            f_amount = st.number_input("Quantidade (unidades, doses):", min_value=0.0, step=1.0, value=1.0)
        with c2:
            f_tipo = st.text_input("Tipo / Modalidade (Musculação, Corrida, Vinho, etc.):")
        with c3:
            f_duracao = st.number_input("Duração em minutos (se treino):", min_value=0.0, step=5.0, value=0.0)
            
        c4, c5 = st.columns(2)
        with c4:
            f_calorias = st.number_input("Calorias estimadas (kcal):", min_value=0.0, step=10.0, value=0.0)
        with c5:
            f_gatilho = st.selectbox("Gatilho Emocional / Situação:", [
                "Nenhum / Rotina",
                "Pós-Reunião / Trabalho",
                "Ansiedade / Início de Semana",
                "Transição de Viagem / Posto",
                "Fim de Noite / Ócio / YouTube",
                "Social / Cerveja",
                "Conflito Emocional / Raiva",
                "Pausa de Estudo"
            ])
            
        f_mood = st.text_input("Estado de Humor / Sentimento:")
        f_nota = st.text_area("Nota contextual do momento:")
        
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
            st.success("Registro salvo com sucesso!")
            st.rerun()

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

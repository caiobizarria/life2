import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from streamlit_gsheets import GSheetsConnection
from datetime import datetime, timedelta, date, time
import random
import uuid

st.set_page_config(
    page_title="Life Logger - Hábitos & Rotina",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Trava de zoom nos gráficos para navegação fluida em telas touch
PLOTLY_CONFIG = {
    'scrollZoom': False,
    'displayModeBar': False,
    'doubleClick': False,
    'showAxisDragHandles': False
}

def lock_chart_zoom(fig):
    fig.update_layout(
        xaxis=dict(fixedrange=True),
        yaxis=dict(fixedrange=True),
        dragmode=False
    )
    return fig

# -------------------------------------------------------------
# CONEXÃO COM GOOGLE SHEETS
# -------------------------------------------------------------
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Erro ao inicializar conexão com Google Sheets: {e}")
    st.stop()

COLUNAS_HABITS = [
    "id", "timestamp", "categoria", "local", "amount", 
    "tipo", "duracao", "calorias", "mood", "gatilho", "nota"
]

COLUNAS_SOS = [
    "id", "timestamp", "local", "acao_escolhida", "conseguiu_evitar"
]

def load_habits():
    try:
        # ttl=0 garante que qualquer edição manual na planilha apareça na hora
        df = conn.read(worksheet=0, ttl=0)
        if df is None or df.empty or df.dropna(how="all").empty:
            return pd.DataFrame(columns=COLUNAS_HABITS)
        df = df.dropna(how="all")
        for col in COLUNAS_HABITS:
            if col not in df.columns:
                df[col] = None
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df['duracao'] = pd.to_numeric(df['duracao'], errors='coerce')
        df['calorias'] = pd.to_numeric(df['calorias'], errors='coerce')
        df['dt'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['dt'])
        if df.empty:
            return pd.DataFrame(columns=COLUNAS_HABITS)
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
        return df.sort_values('dt', ascending=False).reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=COLUNAS_HABITS)

def save_habits(df_to_save):
    try:
        df_clean = df_to_save[COLUNAS_HABITS].copy().fillna("")
        df_clean = df_clean.astype(str)
        conn.update(worksheet=0, data=df_clean)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar na planilha: {e}")
        return False

def load_sos():
    try:
        df = conn.read(worksheet=1, ttl=0)
        if df is None or df.empty or df.dropna(how="all").empty:
            return pd.DataFrame(columns=COLUNAS_SOS)
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame(columns=COLUNAS_SOS)

def save_sos(df_to_save):
    try:
        df_clean = df_to_save[COLUNAS_SOS].copy().fillna("")
        df_clean = df_clean.astype(str)
        conn.update(worksheet=1, data=df_clean)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar SOS: {e}")
        return False

def get_current_location():
    return st.session_state.get("current_location", "São Paulo")

def set_current_location(loc):
    st.session_state["current_location"] = loc

def log_event_direct(categoria, amount=None, tipo=None, duracao=None, calorias=None, mood=None, gatilho=None, nota=None, local_override=None, dt_custom=None):
    loc = local_override if local_override else get_current_location()
    dt_str = dt_custom if dt_custom else (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    
    df_cur = load_habits()
    new_row = pd.DataFrame([{
        "id": str(uuid.uuid4())[:8],
        "timestamp": dt_str,
        "categoria": categoria,
        "local": loc,
        "amount": amount,
        "tipo": tipo,
        "duracao": duracao,
        "calorias": calorias,
        "mood": mood,
        "gatilho": gatilho,
        "nota": nota
    }])
    if df_cur.empty:
        df_updated = new_row
    else:
        df_updated = pd.concat([new_row, df_cur[COLUNAS_HABITS]], ignore_index=True)
    return save_habits(df_updated)

def log_sos_tentativa(acao, conseguiu):
    loc = get_current_location()
    now_str = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    df_sos = load_sos()
    new_row = pd.DataFrame([{
        "id": str(uuid.uuid4())[:8],
        "timestamp": now_str,
        "local": loc,
        "acao_escolhida": acao,
        "conseguiu_evitar": 1 if conseguiu else 0
    }])
    df_updated = pd.concat([new_row, df_sos], ignore_index=True) if not df_sos.empty else new_row
    save_sos(df_updated)

# -------------------------------------------------------------
# MODAL SOS ANTIFUMO
# -------------------------------------------------------------
FRASES_MOTIVACIONAIS = [
    "A vontade aguda dura apenas entre 3 a 5 minutos. Espere a onda passar!",
    "O cigarro não resolve a tensão do dia, ele apenas cria a abstinência do próximo maço.",
    "Você já treinou e correu com dedicação nesta semana. Preserve sua capacidade pulmonar.",
    "A fissura é o cérebro pedindo dopamina rápida. Escolha uma pausa que construa você.",
    "Oxigênio e presença aliviam a ansiedade muito mais rápido que fumaça. Respire fundo."
]

@st.dialog("🛑 Pensando em Fumar? Respire Primeiro.")
def modal_sos_cigarro():
    if "frase_momento" not in st.session_state:
        st.session_state["frase_momento"] = random.choice(FRASES_MOTIVACIONAIS)
        
    st.info(f"💡 **Ponto de Consciência:**\n\n*{st.session_state['frase_momento']}*")
    
    st.markdown("### O que você vai fazer agora para quebrar o impulso?")
    opcoes_sos = [
        "🎵 Ouvir uma música relaxante",
        "🧘 Meditar por 5 minutos",
        "🐾 Pupa para descomprimir",
        "💧 Beber 1 copo de água gelada",
        "🫁 Respiração 4-7-8 (4 ciclos)",
        "🚶 Sair da tela e caminhar um pouco",
        "☕ Café sem cigarro / Goma de mascar"
    ]
    
    acao_selecionada = st.radio("Selecione sua estratégia:", opcoes_sos, index=0)
    
    st.divider()
    st.markdown("**Qual foi o resultado?**")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💪 Consegui não fumar!", use_container_width=True, type="primary"):
            log_sos_tentativa(acao=acao_selecionada, conseguiu=True)
            st.session_state.pop("frase_momento", None)
            st.toast("Vitória registrada no Google Sheets!", icon="🔥")
            st.rerun()
            
    with col2:
        if st.button("😔 Não consegui / Fumei", use_container_width=True):
            log_sos_tentativa(acao=acao_selecionada, conseguiu=False)
            log_event_direct(categoria="Cigarro", amount=1, gatilho=f"Fissura após: {acao_selecionada}")
            st.session_state.pop("frase_momento", None)
            st.toast("Registrado com consciência no Google Sheets!", icon="🚬")
            st.rerun()

# -------------------------------------------------------------
# SIDEBAR
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

if st.sidebar.button("🛑 Pensando em Fumar?", use_container_width=True, type="primary"):
    modal_sos_cigarro()

df_sos_all = load_sos()
if not df_sos_all.empty and 'conseguiu_evitar' in df_sos_all.columns:
    tot_sos = len(df_sos_all)
    vit_sos = int(pd.to_numeric(df_sos_all['conseguiu_evitar'], errors='coerce').fillna(0).sum())
    taxa_sos = (vit_sos / tot_sos) * 100 if tot_sos > 0 else 0
    st.sidebar.caption(f"🛡️ **SOS Usado:** {tot_sos}x | **Vitórias:** {vit_sos} ({taxa_sos:.0f}%)")

st.sidebar.divider()
st.sidebar.subheader("⚡ Registro Rápido (Hoje)")

c_col1, c_col2 = st.sidebar.columns([3, 2])
with c_col1:
    if st.button("🚬 +1 Cigarro", use_container_width=True):
        if log_event_direct(categoria="Cigarro", amount=1):
            st.toast(f"+1 Cigarro em {curr_loc} salvo!", icon="🚬")
            st.rerun()
with c_col2:
    if st.button("🚬 +2", use_container_width=True):
        if log_event_direct(categoria="Cigarro", amount=2):
            st.toast(f"+2 Cigarros em {curr_loc} salvos!", icon="🚬")
            st.rerun()

st.sidebar.caption("🏋️‍♂️ Treinos Rápidos")
col_e1, col_e2 = st.sidebar.columns(2)
with col_e1:
    if st.button("🏋️ Musculação", help="45 min - 350 kcal", use_container_width=True):
        if log_event_direct(categoria="Exercício", tipo="Musculação", duracao=45, calorias=350, amount=1):
            st.toast("Musculação salva!", icon="💪")
            st.rerun()
with col_e2:
    if st.button("🏃 Corrida", help="5km - 45 min", use_container_width=True):
        if log_event_direct(categoria="Exercício", tipo="Corrida", duracao=45, calorias=450, amount=1, nota="5km"):
            st.toast("Corrida salva!", icon="🏃")
            st.rerun()

col_e3, col_e4 = st.sidebar.columns(2)
with col_e3:
    if st.button("🏀 Basquete", use_container_width=True):
        if log_event_direct(categoria="Exercício", tipo="Basquete", duracao=45, calorias=600, amount=1):
            st.toast("Basquete salvo!", icon="🏀")
            st.rerun()
with col_e4:
    if st.button("🚴 Bike", use_container_width=True):
        if log_event_direct(categoria="Exercício", tipo="Ciclismo", duracao=60, calorias=500, amount=1):
            st.toast("Pedal salvo!", icon="🚴")
            st.rerun()

st.sidebar.caption("🍻 Bebidas")
col_b1, col_b2 = st.sidebar.columns(2)
with col_b1:
    if st.button("🍺 Cerveja", use_container_width=True):
        if log_event_direct(categoria="Bebida", tipo="Cerveja", amount=1):
            st.toast("+1 Cerveja salva!", icon="🍺")
            st.rerun()
with col_b2:
    if st.button("🍷 Vinho", use_container_width=True):
        if log_event_direct(categoria="Bebida", tipo="Vinho", amount=1):
            st.toast("+1 Taça salva!", icon="🍷")
            st.rerun()

# -------------------------------------------------------------
# ABAS PRINCIPAIS
# -------------------------------------------------------------
tab_semana, tab_retroativo, tab_evolucao, tab_novo, tab_editar, tab_dados = st.tabs([
    "📅 Visão Semanal", 
    "⚡ Lançar Dia Inteiro (Passado)",
    "📈 Evolução & Histórico", 
    "📝 Registro Detalhado", 
    "✏️ Editar / Deletar Linha",
    "🗄️ Dados na Nuvem"
])

df = load_habits()

# -------------------------------------------------------------
# TAB 1: VISÃO SEMANAL
# -------------------------------------------------------------
with tab_semana:
    st.header("Acompanhamento Semanal")
    st.caption("Conectado diretamente ao Google Sheets em tempo real.")
    
    if df.empty:
        st.info("Sua planilha está pronta. Faça o primeiro registro pelos atalhos laterais ou lance os dias passados na aba ao lado!")
    else:
        todas_semanas = sorted(df['semana_inicio'].unique(), reverse=True)
        semanas_dict = {
            s: f"Semana de {s.strftime('%d/%m/%Y')} a {(s + timedelta(days=6)).strftime('%d/%m/%Y')}"
            for s in todas_semanas
        }
        
        col_filtro, col_metric = st.columns([2, 2])
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
            st.subheader("Cigarros por Dia")
            cigs_dias = cigs_sem.groupby('dia_semana')['amount'].sum().reindex(dias_ordem, fill_value=0).reset_index()
            fig_sem_c = px.bar(
                cigs_dias, x='dia_semana', y='amount', 
                labels={'dia_semana': 'Dia', 'amount': 'Cigarros'},
                text='amount',
                color='amount',
                color_continuous_scale='Reds'
            )
            fig_sem_c.update_traces(textposition='outside')
            fig_sem_c = lock_chart_zoom(fig_sem_c)
            st.plotly_chart(fig_sem_c, use_container_width=True, config=PLOTLY_CONFIG)
            
        with g2:
            st.subheader("Treinos por Dia")
            exs_dias = exs_sem.groupby('dia_semana')['id'].count().reindex(dias_ordem, fill_value=0).reset_index()
            fig_sem_e = px.bar(
                exs_dias, x='dia_semana', y='id', 
                labels={'dia_semana': 'Dia', 'id': 'Treinos'},
                text='id',
                color='id',
                color_continuous_scale='Greens'
            )
            fig_sem_e.update_traces(textposition='outside')
            fig_sem_e = lock_chart_zoom(fig_sem_e)
            st.plotly_chart(fig_sem_e, use_container_width=True, config=PLOTLY_CONFIG)
            
        st.subheader("Eventos Desta Semana")
        cols_view = ['timestamp', 'categoria', 'local', 'tipo', 'amount', 'duracao', 'gatilho', 'mood', 'nota']
        st.dataframe(df_sem[cols_view], use_container_width=True)

# -------------------------------------------------------------
# TAB 2: LANÇAR DIA INTEIRO (RETROATIVO INTELIGENTE)
# -------------------------------------------------------------
with tab_retroativo:
    st.header("⚡ Lançar Dia Completo (Segunda, Terça, Quarta...)")
    st.markdown("Preencha o total consolidado de qualquer dia em um único formulário.")
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        data_alvo = st.date_input("Escolha a Data do Dia:", value=date.today() - timedelta(days=1))
    with col_d2:
        local_dia = st.selectbox("Local onde passou o dia:", loc_options, index=0)
        
    # Mostra o que já está lançado nesse dia para não duplicar sem querer
    df_dia_existente = df[df['data_apenas'] == data_alvo] if not df.empty and 'data_apenas' in df.columns else pd.DataFrame()
    if not df_dia_existente.empty:
        cigs_ja = int(df_dia_existente[df_dia_existente['categoria'] == 'Cigarro']['amount'].sum())
        treinos_ja = len(df_dia_existente[df_dia_existente['categoria'] == 'Exercício'])
        st.info(f"ℹ️ **Nesse dia já constam:** {cigs_ja} cigarros e {treinos_ja} treinos registrados.")
    
    with st.form("form_dia_fechado"):
        st.subheader("1. Cigarros Fumados no Dia")
        cigs_qtd = st.number_input("Total de cigarros fumados no dia:", min_value=0, step=1, value=0)
        gatilho_dia = st.selectbox("Gatilho principal desse dia:", [
            "Nenhum / Rotina", "Pós-Reunião / Trabalho", "Ansiedade / Início de Semana", 
            "Transição de Viagem / Posto", "Fim de Noite / Ócio / YouTube", 
            "Social / Cerveja", "Conflito Emocional / Raiva"
        ])
        
        st.subheader("2. Exercício / Treino do Dia")
        fez_treino = st.checkbox("Teve treino nesse dia?")
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            treino_mod = st.selectbox("Modalidade:", ["Musculação", "Corrida", "Basquete", "Ciclismo", "Yoga", "Outro"], disabled=not fez_treino)
        with col_t2:
            treino_dur = st.number_input("Duração em minutos:", min_value=0, step=5, value=45, disabled=not fez_treino)
        with col_t3:
            treino_cal = st.number_input("Calorias gastas (kcal):", min_value=0, step=10, value=350, disabled=not fez_treino)
            
        st.subheader("3. Bebidas & Observações")
        bebidas_qtd = st.number_input("Bebidas alcoólicas (doses / garrafas):", min_value=0, step=1, value=0)
        nota_dia = st.text_area("Observação sobre o dia / Humor:")
        
        btn_gravar_dia = st.form_submit_button("🚀 Gravar Dia no Google Sheets", use_container_width=True, type="primary")
        if btn_gravar_dia:
            novas_linhas = []
            dia_str = data_alvo.strftime('%Y-%m-%d')
            
            if cigs_qtd > 0:
                novas_linhas.append({
                    "id": str(uuid.uuid4())[:8],
                    "timestamp": f"{dia_str} 18:00:00",
                    "categoria": "Cigarro",
                    "local": local_dia,
                    "amount": cigs_qtd,
                    "tipo": None,
                    "duracao": None,
                    "calorias": None,
                    "mood": None,
                    "gatilho": gatilho_dia if gatilho_dia != "Nenhum / Rotina" else None,
                    "nota": nota_dia if nota_dia else None
                })
                
            if fez_treino and treino_dur > 0:
                novas_linhas.append({
                    "id": str(uuid.uuid4())[:8],
                    "timestamp": f"{dia_str} 16:00:00",
                    "categoria": "Exercício",
                    "local": local_dia,
                    "amount": 1,
                    "tipo": treino_mod,
                    "duracao": treino_dur,
                    "calorias": treino_cal,
                    "mood": None,
                    "gatilho": None,
                    "nota": "Lançamento em lote do dia"
                })
                
            if bebidas_qtd > 0:
                novas_linhas.append({
                    "id": str(uuid.uuid4())[:8],
                    "timestamp": f"{dia_str} 21:00:00",
                    "categoria": "Bebida",
                    "local": local_dia,
                    "amount": bebidas_qtd,
                    "tipo": "Bebida",
                    "duracao": None,
                    "calorias": None,
                    "mood": None,
                    "gatilho": None,
                    "nota": None
                })
                
            if novas_linhas:
                df_cur = load_habits()
                df_novas = pd.DataFrame(novas_linhas)
                df_updated = pd.concat([df_novas, df_cur[COLUNAS_HABITS]], ignore_index=True) if not df_cur.empty else df_novas
                if save_habits(df_updated):
                    st.success(f"Dia {data_alvo.strftime('%d/%m/%Y')} gravado com sucesso no Google Sheets!")
                    st.rerun()
            else:
                st.warning("Preencha pelo menos um hábito (cigarro, treino ou bebida) para salvar.")

# -------------------------------------------------------------
# TAB 3: EVOLUÇÃO HISTÓRICA
# -------------------------------------------------------------
with tab_evolucao:
    st.header("Evolução Semanal Comparativa")
    if not df.empty:
        sem_cigarros = df[df['categoria'] == 'Cigarro'].groupby('semana_inicio')['amount'].sum().reset_index()
        sem_cigarros.columns = ['semana', 'total_cigarros']
        
        sem_treinos = df[df['categoria'] == 'Exercício'].groupby('semana_inicio')['id'].count().reset_index()
        sem_treinos.columns = ['semana', 'total_treinos']
        
        sem_df = pd.merge(sem_cigarros, sem_treinos, on='semana', how='outer').fillna(0).sort_values('semana')
        sem_df['semana_txt'] = sem_df['semana'].apply(lambda d: d.strftime('%d/%m'))
        
        media_cigarros = sem_df['total_cigarros'].mean()
        media_treinos = sem_df['total_treinos'].mean()
        
        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("📊 Média Cigarros/Semana", f"{media_cigarros:.1f}")
        c_m2.metric("📊 Média Treinos/Semana", f"{media_treinos:.1f}")
        c_m3.metric("📅 Semanas Mapeadas", f"{len(sem_df)}")
        
        c_evo1, c_evo2 = st.columns(2)
        with c_evo1:
            fig_evo_cig = go.Figure()
            fig_evo_cig.add_trace(go.Bar(x=sem_df['semana_txt'], y=sem_df['total_cigarros'], name="Semana", marker_color="#E11D48"))
            fig_evo_cig.add_trace(go.Scatter(x=sem_df['semana_txt'], y=[media_cigarros]*len(sem_df), mode='lines', name="Média", line=dict(color='#0F172A', width=3, dash='dash')))
            fig_evo_cig = lock_chart_zoom(fig_evo_cig)
            st.plotly_chart(fig_evo_cig, use_container_width=True, config=PLOTLY_CONFIG)
            
        with c_evo2:
            fig_evo_ex = go.Figure()
            fig_evo_ex.add_trace(go.Bar(x=sem_df['semana_txt'], y=sem_df['total_treinos'], name="Semana", marker_color="#10B981"))
            fig_evo_ex.add_trace(go.Scatter(x=sem_df['semana_txt'], y=[media_treinos]*len(sem_df), mode='lines', name="Média", line=dict(color='#0F172A', width=3, dash='dash')))
            fig_evo_ex = lock_chart_zoom(fig_evo_ex)
            st.plotly_chart(fig_evo_ex, use_container_width=True, config=PLOTLY_CONFIG)

# -------------------------------------------------------------
# TAB 4: NOVO REGISTRO AVULSO
# -------------------------------------------------------------
with tab_novo:
    st.header("Novo Registro Avulso (Data e Hora Personalizadas)")
    with st.form("form_registro_avulso", clear_on_submit=True):
        col_dt1, col_dt2 = st.columns(2)
        with col_dt1:
            data_reg = st.date_input("Data do Registro:", value=date.today())
        with col_dt2:
            hora_reg = st.time_input("Horário aproximado:", value=datetime.now().time())
            
        dt_custom_str = f"{data_reg.strftime('%Y-%m-%d')} {hora_reg.strftime('%H:%M:%S')}"
        f_cat = st.selectbox("Categoria:", ["Cigarro", "Exercício", "Bebida", "Humor", "Estudo", "Leitura", "Outro"])
        
        c1, c2, c3 = st.columns(3)
        with c1:
            f_amount = st.number_input("Quantidade:", min_value=0.0, step=1.0, value=1.0)
        with c2:
            f_tipo = st.text_input("Tipo / Modalidade:")
        with c3:
            f_duracao = st.number_input("Duração (min):", min_value=0.0, step=5.0, value=0.0)
            
        c4, c5 = st.columns(2)
        with c4:
            f_calorias = st.number_input("Calorias (kcal):", min_value=0.0, step=10.0, value=0.0)
        with c5:
            f_gatilho = st.selectbox("Gatilho:", [
                "Nenhum / Rotina", "Pós-Reunião / Trabalho", "Ansiedade / Início de Semana", 
                "Transição de Viagem / Posto", "Fim de Noite / Ócio / YouTube", 
                "Social / Cerveja", "Conflito Emocional / Raiva", "Pausa de Estudo"
            ])
            
        f_mood = st.text_input("Humor / Sentimento:")
        f_nota = st.text_area("Nota:")
        
        if st.form_submit_button("Salvar no Google Sheets", use_container_width=True, type="primary"):
            if log_event_direct(
                categoria=f_cat,
                amount=f_amount if f_amount > 0 else None,
                tipo=f_tipo if f_tipo else None,
                duracao=f_duracao if f_duracao > 0 else None,
                calorias=f_calorias if f_calorias > 0 else None,
                mood=f_mood if f_mood else None,
                gatilho=f_gatilho if f_gatilho != "Nenhum / Rotina" else None,
                nota=f_nota if f_nota else None,
                dt_custom=dt_custom_str
            ):
                st.success("Salvo com sucesso!")
                st.rerun()

# -------------------------------------------------------------
# TAB 5: EDITAR / DELETAR
# -------------------------------------------------------------
with tab_editar:
    st.header("Gerenciador de Linhas da Planilha")
    st.caption("Qualquer alteração feita aqui atualiza o Google Sheets imediatamente.")
    
    if df.empty:
        st.info("Nenhum dado encontrado para edição.")
    else:
        def format_record(r):
            tipo_txt = f" - {r['tipo']}" if pd.notnull(r['tipo']) and str(r['tipo']) != 'None' and str(r['tipo']) != '' else ""
            qtd_txt = f" ({int(r['amount'])}x)" if pd.notnull(r['amount']) and r['amount'] > 0 else ""
            nota_prev = f" | {str(r['nota'])[:20]}..." if pd.notnull(r['nota']) and str(r['nota']) != 'None' and len(str(r['nota'])) > 0 else ""
            return f"ID {r['id']} | {str(r['timestamp'])[:16]} | {r['categoria']}{tipo_txt}{qtd_txt}{nota_prev}"
        
        reg_ids = df['id'].astype(str).tolist()
        dict_labels = {str(r['id']): format_record(r) for _, r in df.iterrows()}
        
        sel_id = st.selectbox("Escolha a linha para alterar:", reg_ids, format_func=lambda x: dict_labels.get(x, x))
        reg_atual = df[df['id'].astype(str) == sel_id].iloc[0]
        
        with st.form("form_edicao_sheets"):
            ed_timestamp = st.text_input("Data e Hora:", value=str(reg_atual['timestamp']))
            cats = ["Cigarro", "Exercício", "Bebida", "Humor", "Estudo", "Leitura", "Outro"]
            ed_cat = st.selectbox("Categoria:", cats, index=cats.index(reg_atual['categoria']) if reg_atual['categoria'] in cats else 0)
            ed_amount = st.number_input("Quantidade:", min_value=0.0, step=1.0, value=float(reg_atual['amount']) if pd.notnull(reg_atual['amount']) else 0.0)
            ed_tipo = st.text_input("Tipo / Modalidade:", value=str(reg_atual['tipo']) if pd.notnull(reg_atual['tipo']) and str(reg_atual['tipo']) != 'None' else "")
            ed_nota = st.text_area("Nota:", value=str(reg_atual['nota']) if pd.notnull(reg_atual['nota']) and str(reg_atual['nota']) != 'None' else "")
            
            if st.form_submit_button("Salvar Modificação", use_container_width=True, type="primary"):
                df_all = load_habits()
                mask = df_all['id'].astype(str) == sel_id
                df_all.loc[mask, 'timestamp'] = ed_timestamp
                df_all.loc[mask, 'categoria'] = ed_cat
                df_all.loc[mask, 'amount'] = ed_amount if ed_amount > 0 else None
                df_all.loc[mask, 'tipo'] = ed_tipo if ed_tipo else None
                df_all.loc[mask, 'nota'] = ed_nota if ed_nota else None
                if save_habits(df_all):
                    st.success("Registro atualizado com sucesso no Google Sheets!")
                    st.rerun()
                    
        st.write("---")
        if st.button("🗑️ Excluir Linha Selecionada", type="secondary"):
            df_all = load_habits()
            df_remaining = df_all[df_all['id'].astype(str) != sel_id]
            if save_habits(df_remaining):
                st.toast(f"Registro #{sel_id} excluído!", icon="🗑️")
                st.rerun()

# -------------------------------------------------------------
# TAB 6: DADOS NA NUVEM & RESET TOTAL
# -------------------------------------------------------------
with tab_dados:
    st.header("Dados Conectados ao Google Sheets")
    df_cloud = load_habits()
    st.dataframe(df_cloud, use_container_width=True)
    
    csv_cloud = df_cloud.to_csv(index=False).encode('utf-8')
    st.download_button(label="📥 Baixar Backup CSV", data=csv_cloud, file_name='life_logger_backup.csv', mime='text/csv')
    
    st.divider()
    if st.button("🚨 Resetar Planilha (Apagar Tudo)", type="secondary"):
        df_vazio = pd.DataFrame(columns=COLUNAS_HABITS)
        if save_habits(df_vazio):
            st.toast("Planilha zerada com sucesso!", icon="🧹")
            st.rerun()

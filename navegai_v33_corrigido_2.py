import os
import re
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, select, func
from sqlalchemy.pool import QueuePool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from streamlit_echarts import st_echarts

# ==========================================
# CONFIGURACAO DE LOGGING
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('navegai_v3.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==========================================
# 1. CONFIGURACAO E CONEXAO
# ==========================================
st.set_page_config(page_title="SEPAF - Dep. Planejamento e Gestão Pública", page_icon="⚓", layout="wide")
# ==========================================
# HEADER PRINCIPAL
# ==========================================
st.markdown("""
    <div style="
        background: linear-gradient(90deg, #1a1a2e 0%, #16213e 100%);
        padding: 16px 20px;
        border-radius: 8px;
        border-left: 4px solid #5470c6;
        margin-bottom: 12px;
    ">
        <h1 style="
            margin: 0;
            font-size: 1.4rem;
            font-weight: 600;
            color: #ffffff;
            letter-spacing: 0.3px;
        ">
            SEPAF <span style="color: #5470c6;">|</span> Dep. Planejamento e Gestão Pública
        </h1>
        <p style="
            margin: 4px 0 0 0;
            font-size: 0.8rem;
            color: #a0aec0;
            font-weight: 400;
        ">
            LAB de Controle de Projetos por IA
        </p>
    </div>
""", unsafe_allow_html=True)
load_dotenv()

#  (NOVO - deploy)
DB_HOST = st.secrets.get("DB_HOST", os.getenv("DB_HOST", "localhost"))
DB_PORT = st.secrets.get("DB_PORT", os.getenv("DB_PORT", "3306"))
DB_USER = st.secrets.get("DB_USER", os.getenv("DB_USER", "root"))
DB_PASSWORD = st.secrets.get("DB_PASSWORD", os.getenv("DB_PASSWORD", "congres2026"))
DB_NAME = st.secrets.get("DB_NAME", os.getenv("DB_NAME", "congres_db"))
DB_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

@st.cache_resource(ttl=300)
def get_engine():
    engine = create_engine(
        DB_URI,
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=3,
        pool_timeout=60,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={
            'connect_timeout': 20,
            'read_timeout': 60,
            'write_timeout': 60
        }
    )
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Engine criado e testado com sucesso")
    return engine

try:
    engine = get_engine()
except Exception as e:
    st.error("🚨 FALHA CRITICA DE CONEXAO COM O BANCO DE DADOS 🚨")
    st.warning("Verifique se o banco de dados está acessivel e as credenciais estao corretas")
    st.info(f"Host configurado: {DB_HOST}:{DB_PORT}")


# ==========================================
# 2. METADADOS DAS VIEWS (VERSAO FINAL - 12 views)
# Baseado na estrutura REAL do banco congres_db
# ==========================================
VIEW_METADADOS = {
    "vw_ia_engajamento_acesso_completo": {
        "descricao": "Dados de acesso e engajamento de usuarios com secretaria",
        "colunas": {
            "nome_usuario": {"tipo": "texto", "descricao": "Nome do usuario"},
            "ultimo_acesso": {"tipo": "data", "descricao": "Data do ultimo acesso"},
            "dias_inativo": {"tipo": "inteiro", "descricao": "Dias desde o ultimo acesso"},
            "status_acesso": {"tipo": "texto", "descricao": "Status do acesso"},
            "secretaria": {"tipo": "texto", "descricao": "Secretaria do usuario"},
            "cargo": {"tipo": "texto", "descricao": "Cargo/funcao"},
            "nome_completo": {"tipo": "texto", "descricao": "Nome completo"}
        },
        "colunas_tempo": ["dias_inativo"],
        "filtro_obrigatorio": None,
        "coluna_label": "secretaria",
        "coluna_valor": "dias_inativo"
    },

    "vw_ia_engajamento_acesso": {
        "descricao": "Dados de acesso e engajamento de usuarios",
        "colunas": {
            "nome_usuario": {"tipo": "texto", "descricao": "Nome do usuario"},
            "ultimo_acesso": {"tipo": "data", "descricao": "Data do ultimo acesso"},
            "dias_inativo": {"tipo": "inteiro", "descricao": "Dias desde o ultimo acesso"},
            "status_acesso": {"tipo": "texto", "descricao": "Status do acesso (Ativo/Inativo)"}
        },
        "colunas_tempo": ["dias_inativo"],
        "filtro_obrigatorio": None,
        "coluna_label": "nome_usuario",
        "coluna_valor": "dias_inativo"
    },
    "vw_projetos_inteligencia": {
        "descricao": "Projetos e investimentos por secretaria",
        "colunas": {
            "id_projeto": {"tipo": "inteiro", "descricao": "ID do projeto"},
            "nome": {"tipo": "texto", "descricao": "Nome do projeto"},
            "descricao": {"tipo": "texto", "descricao": "Descricao do projeto"},
            "valor": {"tipo": "decimal", "descricao": "Valor investido"},
            "secretaria": {"tipo": "texto", "descricao": "Secretaria responsavel"},
            "status_projeto": {"tipo": "texto", "descricao": "Status (Em Andamento, Finalizado, etc)"},
            "ano_inicio": {"tipo": "inteiro", "descricao": "Ano de inicio"},
            "dias_desde_inicio": {"tipo": "inteiro", "descricao": "Dias desde o inicio"}
        },
        "colunas_tempo": ["dias_desde_inicio", "ano_inicio"],
        "filtro_obrigatorio": None,
        "coluna_label": "nome",
        "coluna_valor": "valor"
    },
    "vw_projetos_executivo": {
        "descricao": "Visao executiva consolidada de projetos",
        "colunas": {
            "projeto_id": {"tipo": "inteiro", "descricao": "ID do projeto"},
            "nome_projeto": {"tipo": "texto", "descricao": "Nome do projeto"},
            "valor_financeiro": {"tipo": "decimal", "descricao": "Valor financeiro"},
            "secretaria": {"tipo": "texto", "descricao": "Secretaria"},
            "status_projeto": {"tipo": "texto", "descricao": "Status"}
        },
        "colunas_tempo": [],
        "filtro_obrigatorio": None,
        "coluna_label": "nome_projeto",
        "coluna_valor": "valor_financeiro"
    },
    "vw_ia_tarefas_operacional": {
        "descricao": "Tarefas operacionais e prazos",
        "colunas": {
            "tarefa": {"tipo": "texto", "descricao": "Nome da tarefa"},
            "status_texto": {"tipo": "texto", "descricao": "Status atual"},
            "data_inicio": {"tipo": "data", "descricao": "Data de inicio"},
            "prazo_final": {"tipo": "data", "descricao": "Prazo final"},
            "situacao": {"tipo": "texto", "descricao": "Situacao (Atrasada, No Prazo, etc)"}
        },
        "colunas_tempo": ["data_inicio", "prazo_final"],
        "filtro_obrigatorio": None,
        "coluna_label": "tarefa",
        "coluna_valor": None
    },
    "vw_ia_usuarios_secretaria": {
        "descricao": "Total de usuarios por secretaria",
        "colunas": {
            "secretaria": {"tipo": "texto", "descricao": "Nome da secretaria"},
            "total_usuarios": {"tipo": "inteiro", "descricao": "Quantidade de usuarios"}
        },
        "colunas_tempo": [],
        "filtro_obrigatorio": None,
        "coluna_label": "secretaria",
        "coluna_valor": "total_usuarios"
    },
    "vw_ia_indicadores_pem": {
        "descricao": "Indicadores PEM com metas e respostas",
        "colunas": {
            "id_indicador": {"tipo": "inteiro", "descricao": "ID do indicador"},
            "nome_indicador": {"tipo": "texto", "descricao": "Descricao do indicador"},
            "nome_modelo": {"tipo": "texto", "descricao": "Modelo PEM"},
            "nome_item": {"tipo": "texto", "descricao": "Item PEM"},
            "nome_nivel": {"tipo": "texto", "descricao": "Nivel do indicador"},
            "valor_meta": {"tipo": "decimal", "descricao": "Valor da meta"},
            "cardinalidade": {"tipo": "inteiro", "descricao": "Cardinalidade"},
            "valor_resposta": {"tipo": "decimal", "descricao": "Valor respondido"},
            "data_resposta": {"tipo": "data", "descricao": "Data da resposta"},
            "score_snapshot": {"tipo": "inteiro", "descricao": "Score do snapshot"},
            "data_snapshot": {"tipo": "data", "descricao": "Data do snapshot"},
            "secretaria": {"tipo": "texto", "descricao": "Secretaria"},
            "status_indicador": {"tipo": "texto", "descricao": "Status (Atingido/Nao Atingido)"}
        },
        "colunas_tempo": ["data_resposta", "data_snapshot"],
        "filtro_obrigatorio": None,
        "coluna_label": "nome_indicador",
        "coluna_valor": "valor_resposta"
    },
    "vw_ia_tarefas_completa": {
        "descricao": "Tarefas completas com responsaveis e rotinas",
        "colunas": {
            "id_tarefa": {"tipo": "inteiro", "descricao": "ID da tarefa"},
            "titulo_tarefa": {"tipo": "texto", "descricao": "Titulo da tarefa"},
            "descricao_tarefa": {"tipo": "texto", "descricao": "Descricao"},
            "status_tarefa": {"tipo": "inteiro", "descricao": "Status numerico"},
            "prioridade": {"tipo": "inteiro", "descricao": "Prioridade"},
            "prazo_final": {"tipo": "data", "descricao": "Prazo final (deadline)"},
            "data_criacao": {"tipo": "data", "descricao": "Data de criacao"},
            "dias_desde_criacao": {"tipo": "inteiro", "descricao": "Dias desde criacao"},
            "situacao": {"tipo": "texto", "descricao": "Situacao (Atrasada/No Prazo/Concluida)"},
            "responsavel": {"tipo": "texto", "descricao": "Nome do responsavel"},
            "nome_rotina": {"tipo": "texto", "descricao": "Rotina vinculada"},
            "tarefa_dependente": {"tipo": "texto", "descricao": "Tarefa dependente"},
            "secretaria": {"tipo": "texto", "descricao": "Secretaria"}
        },
        "colunas_tempo": ["prazo_final", "data_criacao", "dias_desde_criacao"],
        "filtro_obrigatorio": None,
        "coluna_label": "titulo_tarefa",
        "coluna_valor": None
    },
    "vw_ia_rotinas_usuarios": {
        "descricao": "Rotinas com usuarios vinculados",
        "colunas": {
            "id_rotina": {"tipo": "inteiro", "descricao": "ID da rotina"},
            "nome_rotina": {"tipo": "texto", "descricao": "Nome da rotina"},
            "status_rotina": {"tipo": "inteiro", "descricao": "Status (ativo/inativo)"},
            "data_criacao": {"tipo": "data", "descricao": "Data de criacao"},
            "criador": {"tipo": "texto", "descricao": "Nome do criador"},
            "usuario_vinculado": {"tipo": "texto", "descricao": "Usuario vinculado"},
            "total_itens": {"tipo": "inteiro", "descricao": "Total de itens"},
            "secretaria": {"tipo": "texto", "descricao": "Secretaria"}
        },
        "colunas_tempo": ["data_criacao"],
        "filtro_obrigatorio": None,
        "coluna_label": "nome_rotina",
        "coluna_valor": "total_itens"
    },
    "vw_ia_tags_classificacao": {
        "descricao": "Tags e classificacoes por entidade",
        "colunas": {
            "id_grupo": {"tipo": "inteiro", "descricao": "ID do grupo"},
            "nome_grupo": {"tipo": "texto", "descricao": "Nome do grupo de tags"},
            "id_tag": {"tipo": "inteiro", "descricao": "ID da tag"},
            "nome_tag": {"tipo": "texto", "descricao": "Nome da tag"},
            "tipo_entidade": {"tipo": "texto", "descricao": "Tipo (modulo)"},
            "id_entidade": {"tipo": "inteiro", "descricao": "ID da entidade"},
            "tipo_entidade_label": {"tipo": "texto", "descricao": "Label do tipo"},
            "secretaria": {"tipo": "texto", "descricao": "Secretaria"}
        },
        "colunas_tempo": [],
        "filtro_obrigatorio": None,
        "coluna_label": "nome_tag",
        "coluna_valor": None
    },
    "vw_ia_usuarios_perfil": {
        "descricao": "Perfil completo dos usuarios",
        "colunas": {
            "id_usuario": {"tipo": "inteiro", "descricao": "ID do usuario"},
            "nome_usuario": {"tipo": "texto", "descricao": "Nome do usuario"},
            "scope_id": {"tipo": "inteiro", "descricao": "ID do scope"},
            "data_cadastro": {"tipo": "data", "descricao": "Data de cadastro"},
            "dias_desde_cadastro": {"tipo": "inteiro", "descricao": "Dias desde cadastro"},
            "nome_pessoa": {"tipo": "texto", "descricao": "Nome completo"},
            "cargo": {"tipo": "texto", "descricao": "Cargo/funcao"},
            "assessor": {"tipo": "texto", "descricao": "Assessor"},
            "ativo": {"tipo": "inteiro", "descricao": "Status ativo"},
            "secretaria": {"tipo": "texto", "descricao": "Secretaria"},
            "total_favoritos": {"tipo": "inteiro", "descricao": "Favoritos"},
            "total_rotinas": {"tipo": "inteiro", "descricao": "Rotinas"},
            "total_tarefas_atribuidas": {"tipo": "inteiro", "descricao": "Tarefas"},
            "total_projetos": {"tipo": "inteiro", "descricao": "Projetos"}
        },
        "colunas_tempo": ["data_cadastro", "dias_desde_cadastro"],
        "filtro_obrigatorio": None,
        "coluna_label": "nome_usuario",
        "coluna_valor": "total_projetos"
    },
    "vw_ia_projetos_pm_completa": {
        "descricao": "Projetos PM completos com itens",
        "colunas": {
            "id_projeto": {"tipo": "inteiro", "descricao": "ID"},
            "nome_projeto": {"tipo": "texto", "descricao": "Nome"},
            "descricao_projeto": {"tipo": "texto", "descricao": "Descricao"},
            "status_projeto": {"tipo": "inteiro", "descricao": "Status numerico"},
            "valor_orcamento": {"tipo": "decimal", "descricao": "Valor"},
            "data_inicio": {"tipo": "data", "descricao": "Inicio"},
            "data_fim_previsto": {"tipo": "data", "descricao": "Fim previsto"},
            "data_conclusao": {"tipo": "data", "descricao": "Conclusao"},
            "dias_desde_inicio": {"tipo": "inteiro", "descricao": "Dias desde inicio"},
            "dias_ate_fim": {"tipo": "inteiro", "descricao": "Dias ate fim"},
            "situacao_projeto": {"tipo": "texto", "descricao": "Situacao"},
            "responsavel": {"tipo": "texto", "descricao": "Responsavel"},
            "indicador_principal": {"tipo": "texto", "descricao": "Indicador"},
            "secretaria": {"tipo": "texto", "descricao": "Secretaria"},
            "total_itens": {"tipo": "inteiro", "descricao": "Total de itens"}
        },
        "colunas_tempo": ["data_inicio", "data_fim_previsto", "dias_desde_inicio", "dias_ate_fim"],
        "filtro_obrigatorio": None,
        "coluna_label": "nome_projeto",
        "coluna_valor": "valor_orcamento"
    },
    "vw_ia_engajamento_faixas": {
        "descricao": "Usuarios com faixas temporais pre-calculadas",
        "colunas": {
            "id_usuario": {"tipo": "inteiro", "descricao": "ID"},
            "nome_usuario": {"tipo": "texto", "descricao": "Nome"},
            "data_cadastro": {"tipo": "data", "descricao": "Cadastro"},
            "dias_desde_cadastro": {"tipo": "inteiro", "descricao": "Dias desde cadastro"},
            "faixa_temporal": {"tipo": "texto", "descricao": "Faixa (1-7, 8-20, etc)"},
            "status_acesso": {"tipo": "texto", "descricao": "Status do acesso"},
            "secretaria": {"tipo": "texto", "descricao": "Secretaria"}
        },
        "colunas_tempo": ["dias_desde_cadastro"],
        "filtro_obrigatorio": None,
        "coluna_label": "faixa_temporal",
        "coluna_valor": None
    }
}
# ==========================================
# MAPEAMENTO DE SIGLAS DE SECRETARIAS
# ==========================================
SIGLAS_SECRETARIAS = {
    # Sigla → Padrão LIKE para SQL
    "seides": "%SEIDES%",
    "seinfra": "%SEINFRA%",
    "seplaf": "%SEPAF%",
    "seplan": "%SEPLAN%",
    "seder": "%SDER%",
    "sese": "%SESEG%",
    "seai": "%SEAI%",
    "seap": "%SEAP%",
    "sed": "%SED%",
    "setur": "%SETUR%",
    "sasan": "%SASAN%",
    "sseg": "%SESEG%",
    "sgc": "%SGC%",
    "pgm": "%PGM%",
    "fcn": "%FCN%",
    "ian": "%IAN%",
    "navetran": "%NAVETRAN%",
    "navegantesprev": "%NAVEGANTESPREV%",
    "congres": "%CONGRES%",
    "3neuron": "%3NEURON%",
    "painel": "%Painel Demonstração%",
    "diretoria": "%DIRETORIA%",
    "assessor": "%ASSESSOR%",
    "gerencia": "%GERÊNCIA%",
}

# Sinônimos e variações comuns
SINONIMOS_SECRETARIAS = {
    "inclusao": "seides",
    "desenvolvimento social": "seides",
    "infraestrutura": "seinfra",
    "planejamento": "seplaf",
    "administracao": "seplaf",
    "financas": "seplaf",
    "educacao": "sed",
    "turismo": "setur",
    "seguranca": "sese",
    "agricultura": "seap",
    "pesca": "seap",
    "meio ambiente": "ian",
    "cultura": "fcn",
    "transito": "navetran",
    "vigilancia": "navetran",
    "procuradoria": "pgm",
    "gestao": "sgc",
    "controle": "sgc",
    "agua": "sasan",
    "saneamento": "sasan",
    "articulacao": "seai",
    "interinstitucional": "seai",
    "desenvolvimento economico": "seder",
    "receita": "seder",
    "territorial": "seplan",
    "mobilidade": "seplan",
    "habitacao": "seplan",
}
# Mapeamento de palavras-chave para views (ATUALIZADO com prioridade)
CONTEXTO_VIEW = {
    "distribuicao": "vw_ia_engajamento_faixas",
    "faixa de inatividade": "vw_ia_engajamento_faixas",
    "cada secretaria": "vw_projetos_inteligencia",
    "quantos projetos": "vw_projetos_inteligencia",
    "login": "vw_ia_engajamento_acesso",
    "login dos usuarios": "vw_ia_engajamento_acesso",
    "mais caros": "vw_projetos_inteligencia",
    "maior valor": "vw_projetos_inteligencia",
    "finalizados": "vw_projetos_inteligencia",
    "em elaboracao": "vw_projetos_inteligencia",
    "acesso": "vw_ia_engajamento_acesso",
    "engajamento": "vw_ia_engajamento_acesso",
    "engajamento_acesso_completo": "vw_ia_engajamento_acesso_completo",
    "acesso_completo": "vw_ia_engajamento_acesso_completo",
    "secretaria_acesso": "vw_ia_engajamento_acesso_completo",
    "secretaria usuario": "vw_ia_engajamento_acesso_completo",
    "secretaria usuarios": "vw_ia_engajamento_acesso_completo",
    "usuarios secretaria": "vw_ia_engajamento_acesso_completo",
    "por secretaria": "vw_ia_engajamento_acesso_completo",
    "acesso por secretaria": "vw_ia_engajamento_acesso_completo",
    "ultimo_acesso": "vw_ia_engajamento_acesso_completo",
    "ultimo acesso": "vw_ia_engajamento_acesso_completo",
    "cargo": "vw_ia_engajamento_acesso_completo",
    "nome_completo": "vw_ia_engajamento_acesso_completo",
    "login": "vw_ia_engajamento_acesso",
    "usuario": "vw_ia_engajamento_acesso",
    "usuarios": "vw_ia_engajamento_acesso",
    "inativo": "vw_ia_engajamento_acesso",
    "inativos": "vw_ia_engajamento_acesso",
    "dias": "vw_ia_engajamento_acesso",
    "tempo": "vw_ia_engajamento_acesso",
    "faixa": "vw_ia_engajamento_faixas",
    "faixas": "vw_ia_engajamento_faixas",
    "intervalo": "vw_ia_engajamento_faixas",
    "projeto": "vw_projetos_inteligencia",
    "projetos": "vw_projetos_inteligencia",
    "investimento": "vw_projetos_inteligencia",
    "investimentos": "vw_projetos_inteligencia",
    "financeiro": "vw_projetos_inteligencia",
    "orcamento": "vw_projetos_inteligencia",
    "valor": "vw_projetos_inteligencia",
    "custo": "vw_projetos_inteligencia",
    "gasto": "vw_projetos_inteligencia",
    "em andamento": "vw_projetos_inteligencia",
    "finalizado": "vw_projetos_inteligencia",
    "elaboracao": "vw_projetos_inteligencia",
    "andamento": "vw_projetos_inteligencia",
    "analise": "vw_projetos_inteligencia",
    "executiva": "vw_projetos_inteligencia",
    "executivo": "vw_projetos_inteligencia",
    "panorama": "vw_projetos_inteligencia",
    "consolidado": "vw_projetos_executivo",
    "resumo": "vw_projetos_executivo",
    "tarefa": "vw_ia_tarefas_operacional",
    "tarefas": "vw_ia_tarefas_operacional",
    "prazo": "vw_ia_tarefas_operacional",
    "prazos": "vw_ia_tarefas_operacional",
    "atrasada": "vw_ia_tarefas_operacional",
    "atrasadas": "vw_ia_tarefas_operacional",
    "pendente": "vw_ia_tarefas_operacional",
    "pendentes": "vw_ia_tarefas_operacional",
    "responsavel": "vw_ia_tarefas_completa",
    "rotina": "vw_ia_tarefas_completa",
    "rotinas": "vw_ia_rotinas_usuarios",
    "indicador": "vw_ia_indicadores_pem",
    "indicadores": "vw_ia_indicadores_pem",
    "meta": "vw_ia_indicadores_pem",
    "metas": "vw_ia_indicadores_pem",
    "atingido": "vw_ia_indicadores_pem",
    "snapshot": "vw_ia_indicadores_pem",
    "pem": "vw_ia_indicadores_pem",
    "tag": "vw_ia_tags_classificacao",
    "tags": "vw_ia_tags_classificacao",
    "classificacao": "vw_ia_tags_classificacao",
    "total_usuarios": "vw_ia_usuarios_secretaria",
    "usuarios_secretaria": "vw_ia_usuarios_secretaria",
    "perfil": "vw_ia_usuarios_perfil",
    "cargo": "vw_ia_usuarios_perfil",
    "pessoa": "vw_ia_usuarios_perfil",
    "pessoas": "vw_ia_usuarios_perfil",
    "pm": "vw_ia_projetos_pm_completa",
    "projeto pm": "vw_ia_projetos_pm_completa",
    "itens projeto": "vw_ia_projetos_pm_completa",
    "situacao projeto": "vw_ia_projetos_pm_completa"
}

@dataclass
class ResultadoConsulta:
    texto: str
    grafico: Optional[Dict[str, Any]]
    dataframe: Optional[pd.DataFrame]
    sql_gerado: str
    sucesso: bool
    mostrar_tabela: bool = False
    erro: Optional[str] = None

# ==========================================
# 3. EXTRATOR DE INTENCAO (LLM so extrai JSON)
# CORRECAO: Todas as chaves {{ e }} do JSON escapadas
# ==========================================
class ExtratorIntencao:
    """
    O LLM NUNCA gera SQL. Ele apenas extrai a intencao em JSON estruturado.
    """

    @staticmethod
    def detectar_secretaria(pergunta: str) -> Optional[str]:
        """
        Detecta se a pergunta menciona uma secretaria por sigla ou nome.
        Retorna o padrão LIKE para SQL, ou None se não detectar.
        """
        p = pergunta.lower()
        
        # 1. Busca siglas diretas (ex: "SEIDES", "seides", "SEINFRA")
        for sigla, like_pattern in SIGLAS_SECRETARIAS.items():
            if sigla in p:
                return like_pattern
        
        # 2. Busca sinônimos/nomes completos (ex: "inclusão", "educação")
        for sinonimo, sigla in SINONIMOS_SECRETARIAS.items():
            if sinonimo in p:
                return SIGLAS_SECRETARIAS.get(sigla)
        
        # 3. Busca por partes do nome completo (ex: "secretaria de educacao")
        if "secretaria" in p:
            # Tenta extrair qual secretaria vem depois
            match = re.search(r'secretaria\s+(?:de\s+)?([a-záéíóúãõç\s]+)', p)
            if match:
                nome_extraido = match.group(1).strip()
                # Tenta fazer match com as siglas
                for sigla, like_pattern in SIGLAS_SECRETARIAS.items():
                    if sigla in nome_extraido or nome_extraido in sigla:
                        return like_pattern
        
        return None

    def __init__(self, model_name="gemini-2.5-flash"):
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
        self._init_chain()

    def _init_chain(self):
        # AJUSTE v3.4: 
        prompt_system = """Voce e um extrator de intencoes. Sua unica tarefa e analisar a pergunta do usuario e retornar um JSON estruturado com os parametros da consulta.

REGRAS ABSOLUTAS:
1. NUNCA gere SQL. Apenas JSON.
2. NUNCA invente campos como 'intent', 'action', 'query_type', 'filters', 'fields'. Use APENAS as 7 chaves abaixo.
3. Seja preciso nos numeros e condicoes.
4. Se nao entender a pergunta, retorne: {{"view": "vw_projetos_inteligencia", "operacao": "listar", "colunas": ["*"], "condicoes": null, "ordenacao": null, "limite": null, "grupo": null, "agregacao": null}}
5. Use apenas as views e colunas disponiveis.
6. Se a pergunta mencionar status especifico (ex: 'Em Andamento', 'Finalizado', 'Atrasada'), INCLUA na condicao.
7. Se a pergunta mencionar valores financeiros, projetos, investimentos, USE vw_projetos_inteligencia.
8. Se a pergunta pedir faixas de dias (1-7, 8-20, etc), USE vw_ia_engajamento_faixas.

VIEWS DISPONIVEIS:
- vw_ia_engajamento_acesso_completo: nome_usuario, ultimo_acesso, dias_inativo, status_acesso, secretaria, cargo, nome_completo (USE ESTA quando a pergunta envolver secretaria E acesso/usuario)
- vw_ia_engajamento_acesso: nome_usuario, ultimo_acesso, dias_inativo, status_acesso (USE quando a pergunta for APENAS sobre acesso, sem mencionar secretaria)
- vw_ia_engajamento_faixas: nome_usuario, faixa_temporal, status_acesso, secretaria
- vw_projetos_inteligencia: id_projeto, nome, descricao, valor, secretaria, status_projeto, ano_inicio, dias_desde_inicio
- vw_projetos_executivo: projeto_id, nome_projeto, valor_financeiro, secretaria, status_projeto
- vw_ia_tarefas_operacional: tarefa, status_texto, data_inicio, prazo_final, situacao
- vw_ia_usuarios_secretaria: secretaria, total_usuarios
- vw_ia_indicadores_pem: id_indicador, nome_indicador, nome_modelo, nome_item, nome_nivel, valor_meta, cardinalidade, valor_resposta, data_resposta, score_snapshot, data_snapshot, secretaria, status_indicador
- vw_ia_tarefas_completa: id_tarefa, titulo_tarefa, descricao_tarefa, status_tarefa, prioridade, prazo_final, data_criacao, dias_desde_criacao, situacao, responsavel, nome_rotina, tarefa_dependente, secretaria
- vw_ia_rotinas_usuarios: id_rotina, nome_rotina, status_rotina, data_criacao, criador, usuario_vinculado, total_itens, secretaria
- vw_ia_tags_classificacao: id_grupo, nome_grupo, id_tag, nome_tag, tipo_entidade, id_entidade, tipo_entidade_label, secretaria
- vw_ia_usuarios_perfil: id_usuario, nome_usuario, scope_id, data_cadastro, dias_desde_cadastro, nome_pessoa, cargo, assessor, ativo, secretaria, total_favoritos, total_rotinas, total_tarefas_atribuidas, total_projetos
- vw_ia_projetos_pm_completa: id_projeto, nome_projeto, descricao_projeto, status_projeto, valor_orcamento, data_inicio, data_fim_previsto, data_conclusao, dias_desde_inicio, dias_ate_fim, situacao_projeto, responsavel, indicador_principal, secretaria, total_itens

FORMATO OBRIGATORIO - USE EXATAMENTE ESTAS 7 CHAVES:
{{"view": "nome_da_view", "operacao": "listar|filtrar|agregar|ranking|contar", "colunas": ["*"], "condicoes": {{"campo": "nome_coluna", "operador": "<=", "valor": 20}}, "ordenacao": {{"campo": "dias_inativo", "direcao": "ASC"}}, "limite": 50, "grupo": null, "agregacao": null}}

EXEMPLOS CORRETOS:
P: "usuarios que acessaram igual ou menor que 20 dias"
R: {{"view": "vw_ia_engajamento_acesso", "operacao": "filtrar", "colunas": ["*"], "condicoes": {{"campo": "dias_inativo", "operador": "<=", "valor": 20}}, "ordenacao": {{"campo": "dias_inativo", "direcao": "ASC"}}, "limite": null, "grupo": null, "agregacao": null}}

P: "top 3 projetos mais caros"
R: {{"view": "vw_projetos_inteligencia", "operacao": "ranking", "colunas": ["nome", "secretaria", "valor"], "condicoes": null, "ordenacao": {{"campo": "valor", "direcao": "DESC"}}, "limite": 3, "grupo": null, "agregacao": null}}

P: "tarefas atrasadas"
R: {{"view": "vw_ia_tarefas_operacional", "operacao": "filtrar", "colunas": ["*"], "condicoes": {{"campo": "situacao", "operador": "=", "valor": "Atrasada"}}, "ordenacao": null, "limite": null, "grupo": null, "agregacao": null}}

P: "projetos em andamento"
R: {{"view": "vw_projetos_inteligencia", "operacao": "filtrar", "colunas": ["*"], "condicoes": {{"campo": "status_projeto", "operador": "=", "valor": "Em Andamento"}}, "ordenacao": null, "limite": null, "grupo": null, "agregacao": null}}

P: "analise executiva da secretaria de educacao"
R: {{"view": "vw_projetos_inteligencia", "operacao": "filtrar", "colunas": ["*"], "condicoes": {{"campo": "secretaria", "operador": "=", "valor": "SED - SECRETARIA DE EDUCACAO"}}, "ordenacao": null, "limite": null, "grupo": null, "agregacao": null}}

P: "faixa de dias de inatividade"
R: {{"view": "vw_ia_engajamento_faixas", "operacao": "agregar", "colunas": ["*"], "condicoes": null, "ordenacao": null, "limite": null, "grupo": "faixa_temporal", "agregacao": "COUNT"}}

P: "Qual a distribuição de usuários por faixa de inatividade?"
R: {{"view": "vw_ia_engajamento_faixas", "operacao": "agregar", "colunas": ["*"], "condicoes": null, "ordenacao": null, "limite": null, "grupo": "faixa_temporal", "agregacao": "COUNT"}}

P: "Quantos projetos cada secretaria tem em andamento?"
R: {{"view": "vw_projetos_inteligencia", "operacao": "agregar", "colunas": ["*"], "condicoes": {{"campo": "status_projeto", "operador": "=", "valor": "Em Andamento"}}, "ordenacao": null, "limite": null, "grupo": "secretaria", "agregacao": "COUNT"}}

P: "Liste os projetos finalizados com maior valor investido"
R: {{"view": "vw_projetos_inteligencia", "operacao": "ranking", "colunas": ["nome", "secretaria", "valor"], "condicoes": {{"campo": "status_projeto", "operador": "=", "valor": "Finalizado"}}, "ordenacao": {{"campo": "valor", "direcao": "DESC"}}, "limite": null, "grupo": null, "agregacao": null}}

EXEMPLOS ERRADOS (NUNCA FACA ISSO):
ERRADO: {{"intent": "Obter valor total...", "query_type": "aggregation"}}  -- NUNCA use 'intent' ou 'query_type'
ERRADO: {{"action": "query", "entity": "projetos", "filters": [...]}}     -- NUNCA use 'action', 'entity', 'filters'
ERRADO: {{"response": "Aqui estao os dados..."}}                          -- NUNCA retorne texto explicativo

LEMBRE-SE: SEMPRE use APENAS as 7 chaves: view, operacao, colunas, condicoes, ordenacao, limite, grupo, agregacao."""   
        
        prompt_human = """Contexto da view disponivel: {contexto_view}

Pergunta do usuario: {pergunta}

Extraia a intencao em JSON puro (sem markdown, sem crases, sem explicacoes):"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", prompt_system),
            ("human", prompt_human)
        ])
        self.chain = prompt | self.llm | StrOutputParser()

    def extrair(self, pergunta: str, contexto_view: str = "") -> Dict[str, Any]:
        """Extrai intencao e retorna dict Python"""
        try:
            resposta = self.chain.invoke({"pergunta": pergunta, "contexto_view": contexto_view})
            resposta_limpa = resposta.strip()

            # BLOQUEIO DE SEGURANCA: Se o LLM gerou SQL livre (tem SELECT, FROM, WHERE), descarta
            if any(cmd in resposta_limpa.upper() for cmd in ['SELECT', 'FROM', 'WHERE', 'CASE WHEN', 'BETWEEN']):
                logger.warning(f"LLM gerou SQL livre em vez de JSON. Descartando. Resposta: {resposta_limpa[:100]}")
                return self._fallback_intencao(pergunta)

            # Limpa markdown e prefixos
            resposta_limpa = resposta_limpa.strip("`").strip()
            if resposta_limpa.lower().startswith("json"):
                resposta_limpa = resposta_limpa[4:].strip()

            # Tenta parsear JSON
            intencao = json.loads(resposta_limpa)
                        # VALIDACAO RIGIDA: garante que o JSON tem as chaves obrigatorias
            chaves_obrigatorias = {"view", "operacao", "colunas", "condicoes", "ordenacao", "limite", "grupo", "agregacao"}
            chaves_recebidas = set(intencao.keys())
            
            if not chaves_obrigatorias.issubset(chaves_recebidas):
                chaves_faltando = chaves_obrigatorias - chaves_recebidas
                chaves_invalidas = chaves_recebidas - chaves_obrigatorias
                logger.warning(f"LLM retornou JSON invalido. Faltando: {chaves_faltando}, Invalidas: {chaves_invalidas}. JSON: {str(intencao)[:200]}")
                return self._fallback_intencao(pergunta)
            
            # Remove chaves invalidas que o LLM possa ter inventado
            for chave_invalida in chaves_recebidas - chaves_obrigatorias:
                del intencao[chave_invalida]
                logger.warning(f"Removida chave invalida do LLM: {chave_invalida}")

            logger.info(f"Intencao extraida e validada pelo LLM: {intencao}")
            return intencao
        except Exception as e:
            logger.warning(f"LLM falhou na extracao, usando fallback: {e}")
            return self._fallback_intencao(pergunta)

    def _fallback_intencao(self, pergunta: str) -> Dict[str, Any]:
        """Fallback baseado em palavras-chave quando o LLM falha"""
        p = pergunta.lower()

        # PRIORIDADE 0: Faixa/distribuicao → view de faixas (MAIOR prioridade!)
        if any(palavra in p for palavra in ["faixa", "faixas", "distribuicao", "distribuição", "intervalo", "range"]):
            view = "vw_ia_engajamento_faixas"
            
        # PRIORIDADE 1: Secretaria + Acesso → view completa
        elif any(palavra in p for palavra in ["secretaria", "secretarias", "por secretaria", "cada secretaria", "sed ", "saude", "educacao", "infraestrutura"]) and \
             any(palavra in p for palavra in ["acesso", "engajamento", "login", "usuario", "usuarios", "inativo", "inativos", "dias", "tempo", "ultimo acesso"]):
            view = "vw_ia_engajamento_acesso_completo"
            
        # PRIORIDADE 2: Palavras que indicam claramente projetos/financeiro
        elif any(palavra in p for palavra in ["projeto", "projetos", "investimento", "investimentos", 
                            "financeiro", "orcamento", "orcamento", "valor", "custo", 
                            "gasto", "em andamento", "finalizado", "elaboracao", "andamento",
                            "analise", "executiva", "executivo", "panorama"]):
            view = "vw_projetos_inteligencia"
            
        # PRIORIDADE 3: Palavras que indicam usuarios (sem secretaria)
        elif any(palavra in p for palavra in ["acesso", "engajamento", "login", "usuario", "usuarios", 
                            "inativo", "inativos", "dias", "tempo"]):
            view = "vw_ia_engajamento_acesso"
            
        # PRIORIDADE 4: Palavras que indicam tarefas
        elif any(palavra in p for palavra in ["tarefa", "tarefas", "prazo", "prazos", "atrasada", 
                           "atrasadas", "pendente", "pendentes"]):
            view = "vw_ia_tarefas_operacional"
            
        # PRIORIDADE 5: Palavras que indicam indicadores
        elif any(palavra in p for palavra in ["indicador", "indicadores", "meta", "metas", 
                               "atingido", "snapshot", "pem"]):
            view = "vw_ia_indicadores_pem"
            
        # PRIORIDADE 6: Palavras que indicam tags
        elif any(palavra in p for palavra in ["tag", "tags", "classificacao", "classificacao"]):
            view = "vw_ia_tags_classificacao"
            
        else:
            # Fallback generico pelo mapeamento
            view = "vw_projetos_inteligencia"  # Default
            for palavra, v in CONTEXTO_VIEW.items():
                if palavra in p:
                    view = v
                    break

        # Detecta operacao
        operacao = "listar"
        if any(x in p for x in ["top", "maiores", "mais caros", "ranking"]):
            operacao = "ranking"
        elif any(x in p for x in ["total", "soma", "media", "média", "quantos", "quantidade", "contar", "comparativo", "faixa", "faixas", "distribuicao", "distribuição"]):
            operacao = "agregar"
        elif any(x in p for x in ["dias", "tempo", "atrasada", "inativo", "prazo", "igual", "menor", "maior", "em andamento", "finalizado", "exclusivamente", "somente", "apenas"]):
            operacao = "filtrar"

        # Detecta condicao
        condicao = None
        # NOVO: Detecta secretaria mencionada na pergunta
        secretaria_like = self.detectar_secretaria(pergunta)
        if secretaria_like:
            condicao = {"campo": "secretaria", "operador": "LIKE", "valor": secretaria_like}
            logger.info(f"Secretaria detectada na pergunta: {secretaria_like}")


        # Status de projeto
        elif "em andamento" in p:
            condicao = {"campo": "status_projeto", "operador": "=", "valor": "Em Andamento"}
        elif "finalizado" in p or "concluido" in p:
            condicao = {"campo": "status_projeto", "operador": "=", "valor": "Finalizado"}
        elif "elaboracao" in p:
            condicao = {"campo": "status_projeto", "operador": "=", "valor": "Em Elaboracao"}
        elif "suspenso" in p:
            condicao = {"campo": "status_projeto", "operador": "=", "valor": "Suspenso"}
        elif "cancelado" in p:
            condicao = {"campo": "status_projeto", "operador": "=", "valor": "Cancelado"}

        # Status de tarefa
        elif "atrasada" in p or "atrasadas" in p:
            condicao = {"campo": "situacao", "operador": "=", "valor": "Atrasada"}
        elif "pendente" in p or "pendentes" in p:
            condicao = {"campo": "status_texto", "operador": "=", "valor": "Pendente"}
        elif "concluida" in p or "concluidas" in p:
            condicao = {"campo": "situacao", "operador": "=", "valor": "Concluida"}

        # Status de acesso
        elif "inativo" in p or "inativos" in p:
            condicao = {"campo": "status_acesso", "operador": "=", "valor": "Inativo"}
        elif "ativo" in p or "ativos" in p:
            condicao = {"campo": "status_acesso", "operador": "=", "valor": "Ativo"}

        # Condicoes numericas de dias (so se NAO for faixa)
        elif not any(palavra in p for palavra in ["faixa", "faixas", "intervalo", "distribuicao", "distribuição"]):
            match_menor_igual = re.search(r'(?:igual\s+ou\s+menor|menor\s+ou\s+igual)\s+(?:que\s+)?(\d+)', p)
            match_mais = re.search(r'mais\s+(?:de\s+)?(\d+)\s*dias?', p)
            match_dias = re.search(r'(\d+)\s*dias?', p)

            if match_menor_igual:
                condicao = {"campo": "dias_inativo", "operador": "<=", "valor": int(match_menor_igual.group(1))}
            elif match_mais:
                condicao = {"campo": "dias_inativo", "operador": ">", "valor": int(match_mais.group(1))}
            elif match_dias:
                dias = int(match_dias.group(1))
                if any(x in p for x in ["mais", ">", "inativo", "superior", "acima"]):
                    condicao = {"campo": "dias_inativo", "operador": ">", "valor": dias}
                else:
                    condicao = {"campo": "dias_inativo", "operador": "<=", "valor": dias}
    
        # Detecta limite
        limite = None
        match_top = re.search(r'top\s*(\d+)', p)
        if match_top:
            limite = int(match_top.group(1))

        # Detecta ordenacao
        ordenacao = None
        if operacao == "ranking":
            if view in ["vw_projetos_inteligencia", "vw_ia_projetos_pm_completa"]:
                ordenacao = {"campo": "valor", "direcao": "DESC"}
            elif view in ["vw_ia_engajamento_acesso", "vw_ia_engajamento_acesso_completo"]:
                ordenacao = {"campo": "dias_inativo", "direcao": "DESC"}

        # Detecta agregacao
        agregacao = None
        grupo = None
        if operacao == "agregar":
            if view == "vw_ia_engajamento_faixas":
                # CORRECAO: Se menciona secretaria, agrupa por ambas
                if any(s in p for s in ["secretaria", "secretarias", "por secretaria", "cada secretaria"]):
                    grupo = ["faixa_temporal", "secretaria"]
                else:
                    grupo = "faixa_temporal"
                agregacao = "COUNT"
            elif view in ["vw_ia_engajamento_acesso", "vw_ia_engajamento_acesso_completo"]:
                grupo = "status_acesso"
                agregacao = "COUNT"
            elif view in ["vw_projetos_inteligencia", "vw_ia_projetos_pm_completa"]:
                grupo = "secretaria"
                agregacao = "COUNT" if any(x in p for x in ["quantos", "quantidade", "quantas"]) else "SUM"

        return {
            "view": view,
            "operacao": operacao,
            "colunas": ["*"],
            "condicoes": condicao,
            "ordenacao": ordenacao,
            "limite": limite,
            "grupo": grupo,
            "agregacao": agregacao
        }
# ==========================================
# 4. CONSTRUTOR SQL (Python puro, zero LLM)
# ==========================================
class ConstrutorSQL:
    """
    Monta SQL usando string formatting controlada. 
    Nunca concatena input do usuario diretamente.
    """

    OPERADORES_VALIDOS = {"=", "!=", "<", ">", "<=", ">=", "LIKE"}

    @staticmethod
    def construir(intencao: Dict[str, Any], sec_selecionada: str = "Todas", pergunta: str = "") -> str:
        """
        Constroi SQL seguro baseado na intencao estruturada.
        """
        view_nome = intencao.get("view", "vw_projetos_inteligencia")
        colunas = intencao.get("colunas", ["*"])
        condicoes = intencao.get("condicoes")
        ordenacao = intencao.get("ordenacao")
        limite = intencao.get("limite")
        grupo = intencao.get("grupo")
        agregacao = intencao.get("agregacao")

        # Valida view
        if view_nome not in VIEW_METADADOS:
            view_nome = "vw_projetos_inteligencia"

        meta = VIEW_METADADOS[view_nome]
        colunas_disponiveis = set(meta["colunas"].keys())
        filtro_obrigatorio = meta.get("filtro_obrigatorio")

        # DETECAO ESPECIAL: Faixas de dias (ex: "1 a 7 dias", "8 a 16 dias")
        faixas_dias = ConstrutorSQL._detectar_faixas_dias(pergunta)

        # Se detectou faixas de dias, IGNORA condicoes numericas de dias_inativo
        # porque as faixas ja cobrem todo o espectro
        if faixas_dias and condicoes and condicoes.get("campo") == "dias_inativo":
            logger.info(f"Faixas de dias detectadas. Ignorando condicao de filtro dias_inativo={condicoes}")
            condicoes = None

        # Monta SELECT
        if faixas_dias:
            select_part = ConstrutorSQL._montar_select_faixas(view_nome, faixas_dias)
        elif agregacao and grupo:
            # AJUSTE v3.2: Aplica agregacao no SQL
            select_part = ConstrutorSQL._montar_select_agregacao(view_nome, agregacao, grupo, colunas, colunas_disponiveis, pergunta)
        elif colunas == ["*"] or not colunas:
            select_part = "SELECT *"
        else:
            colunas_validas = [c for c in colunas if c in colunas_disponiveis]
            if not colunas_validas:
                colunas_validas = ["*"]
            select_part = f"SELECT {', '.join(colunas_validas)}"
        # Monta FROM
        from_part = f"FROM {view_nome}"

        # Monta WHERE
        where_conditions = []

        # Filtro obrigatorio da view
        if filtro_obrigatorio:
            where_conditions.append(filtro_obrigatorio)

        # Filtro de secretaria
        if sec_selecionada != "Todas" and "secretaria" in colunas_disponiveis:
            sec_safe = sec_selecionada.replace("'", "''")
            if '%' in sec_safe:
                where_conditions.append(f"secretaria = '{sec_safe}'")
            elif len(sec_safe) <= 10:
                where_conditions.append(f"secretaria LIKE '%{sec_safe}%'")
            else:
                where_conditions.append(f"secretaria = '{sec_safe}'")

        # Condicoes da intencao
        if condicoes and isinstance(condicoes, dict):
            campo = condicoes.get("campo")
            operador = str(condicoes.get("operador", "=")).upper()
            valor = condicoes.get("valor")

            if operador not in ConstrutorSQL.OPERADORES_VALIDOS:
                operador = "="

            if campo and campo in colunas_disponiveis and valor is not None:
                tipo_campo = meta["colunas"].get(campo, {}).get("tipo", "texto")

                if tipo_campo in ["inteiro", "decimal"]:
                    try:
                        valor_num = float(valor)
                        where_conditions.append(f"{campo} {operador} {valor_num}")
                    except (ValueError, TypeError):
                        pass
                else:
                    valor_safe = str(valor).replace("'", "''")
                    if operador == "LIKE":
                        where_conditions.append(f"{campo} LIKE '%{valor_safe}%'")
                    else:
                        where_conditions.append(f"{campo} {operador} '{valor_safe}'")

        # Monta WHERE completo
        where_part = ""
        if where_conditions:
            where_part = "WHERE " + " AND ".join(where_conditions)

        # Monta GROUP BY
        group_part = ""
        if grupo:
            if isinstance(grupo, list):
                # Valida cada coluna da lista
                grupos_validos = [g for g in grupo if g in colunas_disponiveis]
                if grupos_validos:
                    group_part = f"GROUP BY {', '.join(grupos_validos)}"
            elif isinstance(grupo, str):
                # Suporta string com vírgula ou coluna única
                grupos = [g.strip() for g in grupo.split(",")]
                grupos_validos = [g for g in grupos if g in colunas_disponiveis]
                if grupos_validos:
                    group_part = f"GROUP BY {', '.join(grupos_validos)}"

        # Monta ORDER BY
        order_part = ""
        if ordenacao and isinstance(ordenacao, dict):
            campo_ord = ordenacao.get("campo")
            direcao = str(ordenacao.get("direcao", "ASC")).upper()
            if campo_ord and campo_ord in colunas_disponiveis and direcao in ["ASC", "DESC"]:
                order_part = f"ORDER BY {campo_ord} {direcao}"

        # Monta LIMIT
        limit_part = ""
        if limite and isinstance(limite, int) and limite > 0:
            limit_part = f"LIMIT {limite}"

        # Monta SQL final
        parts = [p for p in [select_part, from_part, where_part, group_part, order_part, limit_part] if p]
        sql = " ".join(parts)

        logger.info(f"SQL construido: {sql}")
        return sql

    @staticmethod
    def _detectar_faixas_dias(pergunta: str) -> List[Dict]:
        """
        AJUSTE v3.2: Regex corrigido para detectar faixas de dias.
        Ex: '1 a 7 dias', '8 a 16 dias', 'acima de 31 dias', 'nunca acessou'
        Retorna lista de dicts com min, max, label
        """
        p = pergunta.lower()
        faixas = []

        # AJUSTE v3.2: Regex corrigido - aceita "a" com ou sem espacos
        matches = re.findall(r'(\d+)\s*a\s*(\d+)\s*dias?', p)
        for min_dias, max_dias in matches:
            faixas.append({
                "min": int(min_dias),
                "max": int(max_dias),
                "label": f"{min_dias} a {max_dias} dias"
            })

        # Padrao: "acima de X dias" / "mais de X dias"
        match_acima = re.search(r'(?:acima\s+de|mais\s+de)\s+(\d+)\s*dias?', p)
        if match_acima:
            faixas.append({
                "min": int(match_acima.group(1)),
                "max": None,
                "label": f"Acima de {match_acima.group(1)} dias"
            })

        # AJUSTE v3.2: Faixa "nunca acessou" / "0 dias" / "nunca"
        if "nunca" in p or "nunca acessou" in p or "zero" in p or "0 dias" in p:
            faixas.append({
                "min": 0,
                "max": 0,
                "label": "Nunca acessou"
            })

        return faixas

    @staticmethod
    def _montar_select_agregacao(view_nome: str, agregacao: str, grupo, 
                                  colunas: List[str], colunas_disponiveis: set,
                                  pergunta: str = "") -> str:
        """
        AJUSTE v3.3: Monta SELECT com agregacao (SUM, COUNT, AVG, etc).
        Suporta grupo como string ou lista.
        """
        agregacao_upper = agregacao.upper()
        p = pergunta.lower()

        # NORMALIZA grupo para string
        if isinstance(grupo, list):
            grupo_str = ", ".join(grupo)
            grupo_first = grupo[0]
        elif isinstance(grupo, str):
            grupo_str = grupo
            grupo_first = grupo.split(",")[0].strip() if "," in grupo else grupo
        else:
            grupo_str = str(grupo)
            grupo_first = grupo_str

        # DETECCAO INTELIGENTE: Se a pergunta pede "quantos", "quantidade", "numero de"
        # deve usar COUNT, mesmo em views de projetos
        pede_contagem = any(palavra in p for palavra in [
            "quantos", "quantas", "quantidade", "numero de", "número de",
            "contar", "contagem", "total de projetos", "total de tarefas"
        ])

        # Se pede contagem explicitamente, forca COUNT
        if pede_contagem and agregacao_upper in ["SUM", "COUNT"]:
            agregacao_upper = "COUNT"

        # Determina a coluna de valor para agregacao
        coluna_valor = None
        if view_nome in VIEW_METADADOS:
            coluna_valor = VIEW_METADADOS[view_nome].get("coluna_valor")

        # Se nao tem coluna_valor definida, tenta encontrar uma coluna numerica
        if not coluna_valor and colunas != ["*"]:
            for c in colunas:
                if c in colunas_disponiveis:
                    tipo = VIEW_METADADOS[view_nome]["colunas"].get(c, {}).get("tipo", "")
                    if tipo in ["inteiro", "decimal"]:
                        coluna_valor = c
                        break

        # Fallback: se nao achou, usa a primeira coluna disponivel que nao seja o grupo
        if not coluna_valor:
            for c in colunas_disponiveis:
                if c != grupo_first and c not in (grupo if isinstance(grupo, list) else [grupo]):
                    tipo = VIEW_METADADOS[view_nome]["colunas"].get(c, {}).get("tipo", "")
                    if tipo in ["inteiro", "decimal"]:
                        coluna_valor = c
                        break

        # Se ainda nao achou, conta registros
        if not coluna_valor:
            return f"SELECT {grupo_str}, COUNT(*) AS total"

        if agregacao_upper == "COUNT":
            return f"SELECT {grupo_str}, COUNT(*) AS total"
        elif agregacao_upper == "SUM":
            return f"SELECT {grupo_str}, SUM({coluna_valor}) AS total"
        elif agregacao_upper == "AVG":
            return f"SELECT {grupo_str}, AVG({coluna_valor}) AS media"
        elif agregacao_upper == "MAX":
            return f"SELECT {grupo_str}, MAX({coluna_valor}) AS maximo"
        elif agregacao_upper == "MIN":
            return f"SELECT {grupo_str}, MIN({coluna_valor}) AS minimo"
        else:
            return f"SELECT {grupo_str}, COUNT(*) AS total"

    @staticmethod
    def _montar_select_faixas(view_nome: str, faixas: List[Dict]) -> str:
        """
        Monta SELECT com CASE WHEN para cada faixa.
        """
        cases = []
        for faixa in faixas:
            min_d = faixa["min"]
            max_d = faixa["max"]
            label = faixa["label"]

            if max_d is None:
                # Acima de X
                cases.append(f"COUNT(CASE WHEN dias_inativo > {min_d} THEN 1 END) AS '{label}'")
            elif min_d == 0 and max_d == 0:
                # Nunca acessou (NULL ou 0)
                cases.append(f"COUNT(CASE WHEN dias_inativo IS NULL OR dias_inativo = 0 THEN 1 END) AS '{label}'")
            else:
                # Faixa X a Y
                cases.append(f"COUNT(CASE WHEN dias_inativo BETWEEN {min_d} AND {max_d} THEN 1 END) AS '{label}'")

        return "SELECT " + ", ".join(cases)

# ==========================================
# 5. AGENTE SQL
# ==========================================
class AgenteSQL:
    def __init__(self, engine, model_name="gemini-2.5-flash"):
        self.engine = engine
        self.extrator = ExtratorIntencao(model_name)
        self.construtor = ConstrutorSQL()

    def consultar(self, pergunta: str, contexto_schema: str, sec_selecionada: str) -> Tuple[pd.DataFrame, str]:
        """
        Fluxo confiavel: Extrai intencao -> Constroi SQL -> Executa
        """
        try:
            # Passo 1: LLM extrai intencao (JSON seguro)
            intencao = self.extrator.extrair(pergunta)

            # Se o contexto_schema indicar uma view especifica, sobrescreve
            if "VIEW: " in contexto_schema:
                view_contexto = contexto_schema.split("VIEW: ")[1].split(".")[0]
                if view_contexto in VIEW_METADADOS:
                    intencao["view"] = view_contexto

            # Passo 2: Python constroi SQL (100% deterministico)
            sql = self.construtor.construir(intencao, sec_selecionada, pergunta)

            # Passo 3: Executa no banco
            with self.engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)

                # Vacina: converte datetime para string serializavel
                for col in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
                    elif df[col].dtype == 'object':
                        try:
                            sample = df[col].dropna().iloc[0] if not df[col].empty else None
                            if sample and isinstance(sample, (pd.Timestamp, pd.DatetimeIndex)):
                                df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            pass

            return df, sql

        except Exception as e:
            logger.error(f"Erro no pipeline SQL: {e}")
            return self._fallback(pergunta, contexto_schema, sec_selecionada)

    def _fallback(self, pergunta: str, contexto_schema: str, sec_selecionada: str) -> Tuple[pd.DataFrame, str]:
        """Fallback: SELECT * FROM view LIMIT 50"""
        view_nome = "vw_projetos_inteligencia"
        if "VIEW: " in contexto_schema:
            view_nome = contexto_schema.split("VIEW: ")[1].split(".")[0]

        sql = f"SELECT * FROM {view_nome} LIMIT 50"
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            return df, sql
        except Exception:
            return pd.DataFrame(), sql

# ==========================================
# 6. MOTOR DE CALCULO
# ==========================================
class MotorCalculo:
    @staticmethod
    def estatisticas(df: pd.DataFrame, col_valor: str = "valor") -> Dict[str, Any]:
        if df.empty or col_valor not in df.columns:
            return {"total": 0, "media": 0, "max": 0, "min": 0, "count": len(df)}
        valores = pd.to_numeric(df[col_valor], errors='coerce').dropna()
        return {
            "total": float(valores.sum()),
            "media": float(valores.mean()),
            "max": float(valores.max()),
            "min": float(valores.min()),
            "count": int(valores.count())
        }

    @staticmethod
    def agrupar(df: pd.DataFrame, col_agrupar: str, col_valor: str = "valor", operacao: str = "sum") -> pd.DataFrame:
        if col_agrupar not in df.columns or col_valor not in df.columns:
            return pd.DataFrame()
        df = df.copy()
        df[col_valor] = pd.to_numeric(df[col_valor], errors='coerce')
        if operacao == "sum":
            result = df.groupby(col_agrupar)[col_valor].sum()
        elif operacao == "mean":
            result = df.groupby(col_agrupar)[col_valor].mean()
        elif operacao == "count":
            result = df.groupby(col_agrupar)[col_valor].count()
        else:
            result = df.groupby(col_agrupar)[col_valor].sum()
        return result.reset_index().sort_values(col_valor, ascending=False)

    @staticmethod
    def top_n(df: pd.DataFrame, col_valor: str = "valor", n: int = 5) -> pd.DataFrame:
        if col_valor not in df.columns:
            return df
        df = df.copy()
        df[col_valor] = pd.to_numeric(df[col_valor], errors='coerce')
        return df.nlargest(n, col_valor)

# ==========================================
# 7. MOTOR DE VISUALIZACAO
# ==========================================
class MotorVisualizacao:
    @staticmethod
    def pizza(df: pd.DataFrame, col_label: str, col_valor: str, titulo: str = "Distribuicao") -> Optional[Dict]:
        if df.empty or col_label not in df.columns or col_valor not in df.columns:
            return None
        df = df.copy()
        df[col_valor] = pd.to_numeric(df[col_valor], errors='coerce')
        df = df[df[col_valor] > 0].sort_values(col_valor, ascending=False)
        if df.empty:
            return None
        dados = [{"name": str(row[col_label])[:35], "value": round(float(row[col_valor]), 2)} for _, row in df.iterrows()]
        return {
            "backgroundColor": "transparent",
            "title": {"text": titulo, "left": "center", "top": 10, "textStyle": {"color": "#fff", "fontSize": 16}},
            "tooltip": {"trigger": "item", "formatter": "{b}: <br/>R$ {c:,.2f} <br/>({d}%)"},
            "legend": {"type": "scroll", "orient": "vertical", "right": 10, "top": 60, "bottom": 20, "textStyle": {"color": "#ccc"}},
            "series": [{
                "type": "pie", "radius": ["40%", "65%"], "center": ["35%", "55%"],
                "avoidLabelOverlap": True,
                "itemStyle": {"borderRadius": 8, "borderColor": "#1a1a2e", "borderWidth": 2},
                "label": {"show": False},
                "emphasis": {
                    "label": {"show": True, "fontSize": 14, "fontWeight": "bold", "color": "#fff"},
                    "itemStyle": {"shadowBlur": 10, "shadowOffsetX": 0, "shadowColor": "rgba(0,0,0,0.5)"}
                },
                "data": dados
            }]
        }
    @staticmethod
    def barras_horizontais(df: pd.DataFrame, col_label: str, col_valor: str, titulo: str = "Ranking", top_n: int = 10, formato: str = "moeda") -> Optional[Dict]:
        """
        formato: 'moeda' (R$), 'numero' (contagem simples), 'percentual' (%)
        """
        if df.empty or col_label not in df.columns or col_valor not in df.columns:
            return None
        df = df.copy()
        df[col_valor] = pd.to_numeric(df[col_valor], errors='coerce')
        df = df[df[col_valor] > 0].nlargest(top_n, col_valor).sort_values(col_valor, ascending=True)
        if df.empty:
            return None

        nomes = [str(l)[:30] for l in df[col_label]]
        valores = [float(v) for v in df[col_valor]]

        # Formata valores conforme o tipo
        def formatar_valor(valor):
            if formato == "moeda":
                if valor >= 1_000_000_000:
                    return f"R$ {valor/1_000_000_000:.1f}B"
                elif valor >= 1_000_000:
                    return f"R$ {valor/1_000_000:.1f}M"
                elif valor >= 1_000:
                    return f"R$ {valor/1_000:.0f}k"
                else:
                    return f"R$ {valor:,.0f}"
            elif formato == "percentual":
                return f"{valor:.1f}%"
            else:  # numero (contagem)
                if valor >= 1_000_000_000:
                    return f"{valor/1_000_000_000:.1f}B"
                elif valor >= 1_000_000:
                    return f"{valor/1_000_000:.1f}M"
                elif valor >= 1_000:
                    return f"{valor/1_000:.0f}k"
                else:
                    return f"{valor:,.0f}"

        labels_formatados = [formatar_valor(v) for v in valores]

        # CORRECAO CRITICA: Cria array de objetos com label pre-formatado como STRING
        series_data = []
        for i, (val, label) in enumerate(zip(valores, labels_formatados)):
            series_data.append({
                "value": val,
                "label": {
                    "show": True,
                    "position": "right",
                    "formatter": label,  # ← STRING LITERAL, não função!
                    "color": "#fff",
                    "fontSize": 10
                }
            })

        return {
            "backgroundColor": "transparent",
            "title": {
                "text": titulo, 
                "left": "center", 
                "top": 10, 
                "textStyle": {"color": "#fff", "fontSize": 14}
            },
            "grid": {
                "left": "32%",
                "right": "15%",
                "bottom": "5%",
                "top": "15%",
                "containLabel": False
            },
            "xAxis": {
                "type": "value", 
                "axisLabel": {
                    "formatter": "R$ {value:,.0f}" if formato == "moeda" else "{value:,.0f}",
                    "color": "#ccc",
                    "fontSize": 9
                }, 
                "splitLine": {"lineStyle": {"color": "#333"}},
                "max": max(valores) * 1.2
            },
            "yAxis": {
                "type": "category", 
                "data": nomes, 
                "axisLabel": {
                    "color": "#ccc", 
                    "width": 220,
                    "overflow": "truncate",
                    "fontSize": 10
                }, 
                "axisLine": {"lineStyle": {"color": "#555"}},
                "axisTick": {"alignWithLabel": True}
            },
            "series": [{
                "data": series_data,  # ← Array de objetos com label embutido
                "type": "bar", 
                "barMaxWidth": 25,
                "barGap": "30%",
                "itemStyle": {
                    "borderRadius": [0, 4, 4, 0],
                    "color": {
                        "type": "linear", 
                        "x": 0, "y": 0, "x2": 1, "y2": 0,
                        "colorStops": [
                            {"offset": 0, "color": "#83bff6"}, 
                            {"offset": 0.5, "color": "#5470c6"}, 
                            {"offset": 1, "color": "#2b52a3"}
                        ]
                    }
                }
            }]
        }

    @staticmethod
    def barras_empilhadas(df: pd.DataFrame, col_x: str = None, col_y: str = None, col_stack: str = None, titulo: str = "Distribuicao") -> Optional[Dict]:
        """
        Gráfico de barras verticais EMPILHADAS.
        df: DataFrame no formato longo com col_x (eixo X), col_y (valores), col_stack (cores/empilhamento)
        """
        if df.empty or col_x not in df.columns or col_y not in df.columns or col_stack not in df.columns:
            return None

        # Pivot: linhas = faixa_temporal, colunas = secretarias, valores = total
        df_pivot = df.pivot_table(index=col_x, columns=col_stack, values=col_y, fill_value=0, aggfunc='sum')

        categorias = df_pivot.index.tolist()
        series = []

        # Cores para secretarias
        cores = ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de", "#fc8452", "#9a60b4", "#ea7ccc", "#3ba272", "#ff9f7f"]

        for idx, secretaria in enumerate(df_pivot.columns):
            cor = cores[idx % len(cores)]
            series.append({
                "name": str(secretaria)[:30],
                "type": "bar",
                "stack": "total",
                "emphasis": {"focus": "series"},
                "itemStyle": {"borderRadius": [2, 2, 0, 0]},
                "data": [int(v) for v in df_pivot[secretaria].tolist()]
            })

        return {
            "backgroundColor": "transparent",
            "title": {"text": titulo, "left": "center", "top": 10, "textStyle": {"color": "#fff", "fontSize": 16}},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {"textStyle": {"color": "#ccc"}, "top": 40},
            "grid": {"left": "10%", "right": "10%", "bottom": "15%", "top": "20%", "containLabel": True},
            "xAxis": {
                "type": "category", 
                "data": categorias, 
                "axisLabel": {"color": "#ccc", "rotate": 30}, 
                "axisLine": {"lineStyle": {"color": "#555"}}
            },
            "yAxis": {
                "type": "value", 
                "axisLabel": {"color": "#ccc"}, 
                "splitLine": {"lineStyle": {"color": "#333"}}
            },
            "series": series
        }

    @staticmethod
    def barras_verticais(df: pd.DataFrame, col_label: str = None, col_valor: str = None, titulo: str = "Distribuicao") -> Optional[Dict]:
        """
        AJUSTE v3.2: Grafico de barras verticais para faixas temporais.
        Aceita DataFrames com colunas dinamicas (resultado de COUNT(CASE WHEN...)).
        """
        if df.empty:
            return None

        # AJUSTE v3.2: Se o DataFrame tem apenas 1 linha e varias colunas (formato de faixas)
        # Transforma de formato largo para formato longo
        if len(df) == 1 and len(df.columns) > 1:
            # Formato de faixas: cada coluna e uma faixa, valor e a contagem
            categorias = []
            valores = []
            for col in df.columns:
                categorias.append(str(col))
                valores.append(float(df[col].iloc[0]))
        else:
            # Formato normal: col_label e col_valor
            if col_label not in df.columns or col_valor not in df.columns:
                return None
            df = df.copy()
            df[col_valor] = pd.to_numeric(df[col_valor], errors='coerce')
            df = df[df[col_valor] > 0].sort_values(col_valor, ascending=False)
            if df.empty:
                return None
            categorias = [str(l) for l in df[col_label]]
            valores = [float(v) for v in df[col_valor]]

        return {
            "backgroundColor": "transparent",
            "title": {"text": titulo, "left": "center", "top": 10, "textStyle": {"color": "#fff", "fontSize": 16}},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}, "formatter": "{b}: {c} usuarios"},
            "grid": {"left": "10%", "right": "10%", "bottom": "15%", "top": "15%", "containLabel": True},
            "xAxis": {
                "type": "category", 
                "data": categorias, 
                "axisLabel": {"color": "#ccc", "rotate": 30}, 
                "axisLine": {"lineStyle": {"color": "#555"}}
            },
            "yAxis": {
                "type": "value", 
                "axisLabel": {"color": "#ccc"}, 
                "splitLine": {"lineStyle": {"color": "#333"}}
            },
            "series": [{
                "data": valores, 
                "type": "bar", 
                "barMaxWidth": 50,
                "itemStyle": {
                    "borderRadius": [6, 6, 0, 0],
                    "color": {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                              "colorStops": [{"offset": 0, "color": "#83bff6"}, {"offset": 1, "color": "#5470c6"}]}
                },
                "label": {"show": True, "position": "top", "formatter": "{c}", "color": "#fff", "fontSize": 12}
            }]
        }

    @staticmethod
    def barras_status(df: pd.DataFrame, col_status: str = "status_projeto", col_quantidade: str = "quantidade") -> Optional[Dict]:
        if df.empty or col_status not in df.columns:
            return None

        # CORRECAO: Se já temos coluna de quantidade agregada (ex: do SQL COUNT), use-a
        if col_quantidade in df.columns:
            contagem = df[[col_status, col_quantidade]].copy()
            contagem.columns = ["status", "quantidade"]
        else:
            # Fallback: faz value_counts se não tiver quantidade
            contagem = df[col_status].value_counts().reset_index()
            contagem.columns = ["status", "quantidade"]
        
        cores_status = {
            "Em Andamento": "#5470c6", 
            "Finalizado": "#91cc75", 
            "Em Elaboracao": "#fac858", 
            "Em Elaboração": "#fac858",
            "Não Iniciado": "#ee6666",
            "Nao Iniciado": "#ee6666",
            "Outros": "#73c0de",
            "Suspenso": "#fc8452",
            "Cancelado": "#9a60b4"
        }
        
        dados = []
        total = int(contagem["quantidade"].sum())
        
        for _, row in contagem.iterrows():
            status = str(row["status"])
            qtd = int(row["quantidade"])
            pct = round((qtd / total) * 100, 1) if total > 0 else 0
            dados.append({
                "value": qtd, 
                "name": status, 
                "itemStyle": {"color": cores_status.get(status, "#999")}
            })
            
        return {
            "backgroundColor": "transparent", 
            "tooltip": {
                "trigger": "item",
                "formatter": "{b}: {c} projetos ({d}%)"
            }, 
            "series": [{
                "type": "pie", 
                "radius": ["35%", "60%"],
                "center": ["50%", "50%"], 
                "data": dados, 
                "avoidLabelOverlap": True,
                "itemStyle": {
                    "borderRadius": 6,
                    "borderColor": "#1a1a2e",
                    "borderWidth": 2
                },
                "label": {
                    "show": True,
                    "color": "#fff",
                    "formatter": "{b}: {c} ({d}%)"
                },
                "emphasis": {
                    "label": {
                        "show": True,
                        "fontSize": 14,
                        "fontWeight": "bold"
                    },
                    "itemStyle": {
                        "shadowBlur": 10,
                        "shadowOffsetX": 0,
                        "shadowColor": "rgba(0, 0, 0, 0.5)"
                    }
                }
            }]
        }
# ==========================================
# 8. NARRADOR
# ==========================================
class NarradorExecutivo:
    def __init__(self, model_name="gemini-2.5-flash"):
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.1)
        self._init_chain()

    def _init_chain(self):
        system_msg = """Voce e o Analista Executivo da SEPAF Navegantes.
REGRAS ABSOLUTAS:
1. Use os dados fornecidos EXATAMENTE como estao - NUNCA invente, arredonde ou estime
2. Formate valores monetarios como R$ X.XXX.XXX,XX
3. Seja direto, executivo e profissional
4. Inicie SEMPRE com 'Final Answer:'
5. Se nao houver dados, diga 'Final Answer: Nenhum registro localizado.'
6. Mantenha o tom institucional da Prefeitura de Navegantes"""

        human_msg = """Dados estruturados da consulta:
{json_dados}

Pergunta original do usuario: {pergunta}

Gere a resposta executiva em portugues:"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("human", human_msg)
        ])
        self.chain = prompt | self.llm | StrOutputParser()

    def narrar(self, dados: Dict[str, Any], pergunta_original: str) -> str:
        try:
            dados_limitados = self._limitar_dados(dados)
            json_dados_seguro = json.dumps(dados_limitados, ensure_ascii=False, indent=2, default=str)

            resposta = self.chain.invoke({
                "json_dados": json_dados_seguro,
                "pergunta": pergunta_original
            })
            return resposta
        except Exception as e:
            logger.error(f"Erro na narracao: {e}")
            return self._fallback_narrativa(dados)

    def _limitar_dados(self, dados: Dict, max_registros: int = 20) -> Dict:
        dados_copy = dict(dados)
        if "dados_brutos" in dados_copy and len(dados_copy["dados_brutos"]) > max_registros:
            dados_copy["dados_brutos"] = dados_copy["dados_brutos"][:max_registros]
            dados_copy["_nota"] = f"Mostrando {max_registros} de {len(dados['dados_brutos'])} registros"
        return dados_copy

    def _fallback_narrativa(self, dados: Dict) -> str:
        partes = ["Final Answer:"]
        if "estatisticas" in dados:
            est = dados["estatisticas"]
            partes.append(f"Total de registros: {est.get('count', 0)}")
            if est.get('total', 0) > 0:
                partes.append(f"Valor Total: R$ {est.get('total', 0):,.2f}")
            if est.get('media', 0) > 0:
                partes.append(f"Media: R$ {est.get('media', 0):,.2f}")
            if est.get('max', 0) > 0:
                partes.append(f"Maior valor: R$ {est.get('max', 0):,.2f}")
            if est.get('min', 0) > 0:
                partes.append(f"Menor valor: R$ {est.get('min', 0):,.2f}")
        return "\n".join(partes)

# ==========================================
# 9. ORQUESTRADOR
# ==========================================
class OrquestradorNavegAI:
    def __init__(self, engine):
        self.agente_sql = AgenteSQL(engine)
        self.motor_calc = MotorCalculo()
        self.motor_viz = MotorVisualizacao()
        self.narrador = NarradorExecutivo()

    def classificar_intencao(self, pergunta: str) -> Dict[str, Any]:
        pergunta_lower = pergunta.lower()
        resultado = {
            "tipo": "sql_simples", 
            "quer_grafico": False, 
            "tipo_grafico": None, 
            "quer_agregacao": False, 
            "coluna_agrupar": None, 
            "top_n": None,
            "quer_tabela": False
        }

        if any(p in pergunta_lower for p in ["grafico", "gráfico", "pizza", "barras", "visual", "dashboard", "mostre", "mostrar"]):
            resultado["quer_grafico"] = True
            if "pizza" in pergunta_lower:
                resultado["tipo_grafico"] = "pizza"
            elif "barra" in pergunta_lower:
                resultado["tipo_grafico"] = "barras"

        if any(p in pergunta_lower for p in ["tabela", "lista", "relatorio", "relatório", "todos os detalhes"]):
            resultado["quer_tabela"] = True

        # CORRECAO: "distribuicao" e "faixa" devem disparar agregacao
        if any(p in pergunta_lower for p in ["total", "soma", "media", "média", "quantos", "quantidade", "contar", "comparativo", "distribuicao", "distribuição"]):
            resultado["quer_agregacao"] = True
            
        # CORRECAO: "faixa" sozinho tambem dispara agregacao
        if any(p in pergunta_lower for p in ["faixa", "faixas", "intervalo", "range"]):
            resultado["quer_agregacao"] = True

        if any(p in pergunta_lower for p in ["por secretaria", "por secretarias", "cada secretaria"]):
            resultado["coluna_agrupar"] = "secretaria"
        # CORRECAO: "por faixa" agrupa por faixa_temporal
        elif any(p in pergunta_lower for p in ["por faixa", "por faixas", "faixa de"]):
            if any(s in pergunta_lower for s in ["secretaria", "secretarias", "por secretaria", "cada secretaria"]):
                resultado["coluna_agrupar"] = ["faixa_temporal", "secretaria"]
            else:
                resultado["coluna_agrupar"] = "faixa_temporal"

        match = re.search(r'(top\s?\d+|\d+\s?maiores|\d+\s?mais)', pergunta_lower)
        if match:
            num = re.search(r'\d+', match.group())
            if num:
                resultado["top_n"] = int(num.group())

        if resultado["quer_agregacao"] and resultado["coluna_agrupar"]:
            resultado["tipo"] = "agregacao_grupo"
        elif resultado["quer_agregacao"]:
            resultado["tipo"] = "agregacao_simples"
        elif resultado["top_n"]:
            resultado["tipo"] = "ranking"

        return resultado

    def rotear_contexto(self, pergunta: str) -> str:
        p = pergunta.lower()
        # NOVO: Se menciona secretaria específica, adiciona contexto
        secretaria_like = ExtratorIntencao.detectar_secretaria(pergunta)
        if secretaria_like:
            sec_nome = secretaria_like.replace('%', '')
            return f"VIEW: vw_projetos_inteligencia. SECRETARIA: {sec_nome}. COLUNAS: {', '.join(VIEW_METADADOS['vw_projetos_inteligencia']['colunas'].keys())}"
        # PRIORIDADE MAXIMA: Faixa de inatividade → view de faixas
        if any(x in p for x in ["faixa", "faixas", "distribuicao", "distribuição", "intervalo", "range"]):
            return f"VIEW: vw_ia_engajamento_faixas. COLUNAS: {', '.join(VIEW_METADADOS['vw_ia_engajamento_faixas']['colunas'].keys())}"
        # PRIORIDADE 1: Se menciona secretaria + acesso/usuario/log → view completa
        # Esta view tem: nome_usuario, ultimo_acesso, dias_inativo, status_acesso, secretaria, cargo
        menciona_secretaria = any(x in p for x in ["secretaria", "secretarias", "por secretaria", "cada secretaria", "sed", "saude", "educacao", "infraestrutura"])
        menciona_acesso = any(x in p for x in ["acesso", "acessou", "inativo", "tempo", "dias", "fora", "log", "login", "usuario", "usuarios", "engajamento"])
        
        if menciona_secretaria and menciona_acesso:
            return f"VIEW: vw_ia_engajamento_acesso_completo. COLUNAS: {', '.join(VIEW_METADADOS['vw_ia_engajamento_acesso_completo']['colunas'].keys())}"

        if any(x in p for x in ["projeto", "projetos", "investimento", "valor", "analise", "executiva", "executivo", "panorama", "orcamento"]):
            return f"VIEW: vw_projetos_inteligencia. COLUNAS: {', '.join(VIEW_METADADOS['vw_projetos_inteligencia']['colunas'].keys())}"

        if any(x in p for x in ["acesso", "acessou", "inativo", "tempo", "dias", "fora", "log", "login"]):
            return f"VIEW: vw_ia_engajamento_acesso. COLUNAS: {', '.join(VIEW_METADADOS['vw_ia_engajamento_acesso']['colunas'].keys())}"

        if any(x in p for x in ["tarefa", "prazo", "atrasada", "pendente"]):
            return f"VIEW: vw_ia_tarefas_operacional. COLUNAS: {', '.join(VIEW_METADADOS['vw_ia_tarefas_operacional']['colunas'].keys())}"

        if any(x in p for x in ["total_usuarios", "usuarios_secretaria"]):
            return f"VIEW: vw_ia_usuarios_secretaria. COLUNAS: {', '.join(VIEW_METADADOS['vw_ia_usuarios_secretaria']['colunas'].keys())}"

        return f"VIEW: vw_projetos_inteligencia. COLUNAS: {', '.join(VIEW_METADADOS['vw_projetos_inteligencia']['colunas'].keys())}"

    def processar(self, pergunta: str, sec_selecionada: str = "Todas") -> ResultadoConsulta:
        try:
            intencao = self.classificar_intencao(pergunta)
            contexto = self.rotear_contexto(pergunta)
            logger.info(f"Intencao Detectada: {intencao}")
            logger.info(f"Contexto Roteado: {contexto}")

            df, sql = self.agente_sql.consultar(pergunta, contexto, sec_selecionada)

            if df.empty:
                return ResultadoConsulta(
                    texto="Final Answer: Nenhum registro localizado para os filtros informados.",
                    grafico=None, dataframe=df, sql_gerado=sql, sucesso=True
                )

            dados_estruturados = {
                "dados_brutos": df.head(20).to_dict('records'),
                "estatisticas": self.motor_calc.estatisticas(df),
                "intencao_detectada": intencao,
                "total_registros": len(df)
            }

            df_grafico = df
            if intencao["coluna_agrupar"] and intencao["coluna_agrupar"] in df.columns:
                df_agrupado = self.motor_calc.agrupar(df, intencao["coluna_agrupar"])
                if not df_agrupado.empty:
                    dados_estruturados["agrupamento"] = df_agrupado.to_dict('records')
                    df_grafico = df_agrupado
            if intencao["top_n"]:
                df = self.motor_calc.top_n(df, n=intencao["top_n"])
                dados_estruturados["dados_brutos"] = df.to_dict('records')

            grafico = None
            if intencao["quer_grafico"] and not df_grafico.empty:
                # AJUSTE v3.2: Detecta se e formato de faixas (1 linha, multiplas colunas)
                if len(df_grafico) == 1 and len(df_grafico.columns) > 1 and not intencao["coluna_agrupar"]:
                    # Formato de faixas: usa barras_verticais com colunas dinamicas
                    grafico = self.motor_viz.barras_verticais(df_grafico, titulo="Distribuicao por Faixas")
                # CORRECAO: Detecta se precisa de grafico empilhado (faixa + secretaria)
                elif isinstance(intencao.get("coluna_agrupar"), list) and len(intencao["coluna_agrupar"]) == 2:
                    col_x = intencao["coluna_agrupar"][0]
                    col_stack = intencao["coluna_agrupar"][1]
                    col_valor = "total" if "total" in df_grafico.columns else df_grafico.columns[-1]
                    if col_x in df_grafico.columns and col_stack in df_grafico.columns:
                        grafico = self.motor_viz.barras_empilhadas(df_grafico, col_x, col_valor, col_stack, "Distribuicao por Faixa e Secretaria")
                    else:
                        col_label = intencao["coluna_agrupar"][0] if isinstance(intencao["coluna_agrupar"], list) else intencao["coluna_agrupar"]
                        col_valor = "valor" if "valor" in df_grafico.columns else df_grafico.columns[-1]
                        grafico = self.motor_viz.barras_horizontais(df_grafico, col_label, col_valor, "Ranking")
                elif intencao["tipo_grafico"] == "pizza" or (intencao["coluna_agrupar"] and len(df_grafico) <= 12):
                    col_label = intencao["coluna_agrupar"] or df_grafico.columns[0]
                    if isinstance(col_label, list):
                        col_label = col_label[0]
                    col_valor = "valor" if "valor" in df_grafico.columns else df_grafico.columns[-1]
                    grafico = self.motor_viz.pizza(df_grafico, col_label, col_valor, "Distribuicao")
                else:
                    col_label = intencao["coluna_agrupar"] or df_grafico.columns[0]
                    if isinstance(col_label, list):
                        col_label = col_label[0]
                    col_valor = "valor" if "valor" in df_grafico.columns else df_grafico.columns[-1]
                    # Detecta se é contagem (COUNT) para usar formato numero
                    formato = "numero" if intencao.get("quer_agregacao") and not intencao.get("tipo_grafico") == "pizza" else "moeda"
                    grafico = self.motor_viz.barras_horizontais(df_grafico, col_label, col_valor, "Ranking", formato=formato)

            # CORRECAO: Define 'texto' antes de usar no return
            if intencao["quer_tabela"]:
                texto = f"Final Answer: Encontrei {len(df)} registros conforme solicitado. Os dados detalhados estao na tabela interativa abaixo."
            else:
                texto = self.narrador.narrar(dados_estruturados, pergunta)

            return ResultadoConsulta(
                texto=texto, 
                grafico=grafico, 
                dataframe=df, 
                sql_gerado=sql, 
                sucesso=True,
                mostrar_tabela=intencao["quer_tabela"]
            )
        except Exception as e:
            logger.error(f"Erro no pipeline: {e}")
            return ResultadoConsulta(
                texto=f"Final Answer: Erro ao processar consulta: {str(e)}",
                grafico=None, dataframe=None, sql_gerado="", sucesso=False, erro=str(e)
            )

# ==========================================
# 10. INICIALIZACAO
# ==========================================
try:
    orquestrador = OrquestradorNavegAI(engine)
    logger.info("Orquestrador v3.1 inicializado com sucesso")
except Exception as e:
    logger.error(f"Falha ao inicializar orquestrador: {e}")
    st.error("Erro critico na inicializacao do sistema.")
    st.stop()

# ==========================================
# 11. INTERFACE STREAMLIT
# ==========================================
with st.sidebar:
    if os.path.exists("assets/logo_nvt.jpg"):
        st.image("assets/logo_nvt.jpg", width=80)
    st.markdown("""
        <div style="text-align: center; margin-bottom: 8px;">
            <p style="margin: 0; font-size: 0.9rem; color: #fff; font-weight: 600;">⚓ NavegAI v3.2</p>
            <p style="margin: 2px 0 0 0; font-size: 0.65rem; color: #aaa; line-height: 1.2;">
                Arquitetura Determinística<br>
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    if st.button("🗑️ Limpar Conversa", use_container_width=True):
        st.session_state.history = []
        st.rerun()
    st.divider()
    st.subheader("⚙️ Filtro de Unidade")
    try:
        with engine.connect() as conn:
            stmt = select(func.distinct(text("secretaria"))).select_from(text("vw_projetos_inteligencia")).where(text("secretaria IS NOT NULL")).order_by(text("secretaria"))
            res_sec = conn.execute(stmt).fetchall()
            list_sec = ["Todas"] + [r[0] for r in res_sec if r[0]]
    except Exception as e:
        logger.error(f"Erro ao carregar secretarias: {e}")
        list_sec = ["Todas"]
    sec_selecionada = st.selectbox("Secretaria:", list_sec)
    st.divider()
    st.subheader("📊 Indicadores DB Congres")
    st.caption("Maio 2026")
    try:
        with engine.connect() as conn:
            # Usuários Ativos no Sistema
            where_u = "WHERE status_acesso = 'Ativo'"
            params_u = {}
            if sec_selecionada != "Todas":
                where_u += " AND secretaria = :sec"
                params_u["sec"] = sec_selecionada
            n_u = conn.execute(text(f"SELECT COUNT(DISTINCT nome_usuario) FROM vw_ia_engajamento_acesso_completo {where_u}"), params_u).scalar() or 0
            
            # Valor Total dos Projetos
            where_v = "WHERE 1=1"
            params_v = {}
            if sec_selecionada != "Todas":
                where_v += " AND secretaria = :sec"
                params_v["sec"] = sec_selecionada
            v_t = conn.execute(text(f"SELECT COALESCE(SUM(valor), 0) FROM vw_projetos_inteligencia {where_v}"), params_v).scalar() or 0
    except Exception as e:
        logger.error(f"Erro nos KPIs: {e}")
        n_u, v_t = 0, 0
    
    # Layout compacto para sidebar
    kpi_col1, kpi_col2 = st.columns(2)
    with kpi_col1:
        st.markdown(f"""
            <div style="text-align: center;">
                <p style="margin: 0; font-size: 0.7rem; color: #aaa;">👤 Usuários Ativos</p>
                <p style="margin: 0; font-size: 1.4rem; font-weight: 700; color: #fff;">{int(n_u)}</p>
            </div>
        """, unsafe_allow_html=True)
    with kpi_col2:
        # Formata valor em milhões para caber
        v_t_float = float(v_t)
        if v_t_float >= 1_000_000_000:
            v_display = f"R$ {v_t_float/1_000_000_000:.1f}B"
        elif v_t_float >= 1_000_000:
            v_display = f"R$ {v_t_float/1_000_000:.1f}M"
        elif v_t_float >= 1_000:
            v_display = f"R$ {v_t_float/1_000:.0f}k"
        else:
            v_display = f"R$ {v_t_float:,.0f}"
        
        st.markdown(f"""
            <div style="text-align: center;">
                <p style="margin: 0; font-size: 0.7rem; color: #aaa;">💰 Volume Financeiro</p>
                <p style="margin: 0; font-size: 1.2rem; font-weight: 700; color: #fff;">{v_display}</p>
            </div>
        """, unsafe_allow_html=True)
    
    st.caption("v3.2 | Arquitetura Determinística")
tab_dash, tab_chat, tab_prompts = st.tabs(["📈 Dashboard Executivo", "💬 Consultar Inteligencia", "💡 Prompts de Valor"])

with tab_dash:
    st.header(f"Panorama Estrategico: {sec_selecionada}")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Distribuição de Status")
        try:
            with engine.connect() as conn:
                where_d = ""
                params_d = {}
                if sec_selecionada != "Todas":
                    where_d = "WHERE secretaria = :sec"
                    params_d["sec"] = sec_selecionada
                
                # MESMA QUERY para tabela E gráfico
                sql_status = f"""
                    SELECT 
                        status_projeto AS status,
                        COUNT(*) AS quantidade
                    FROM vw_projetos_inteligencia 
                    {where_d} 
                    GROUP BY status_projeto
                    ORDER BY quantidade DESC
                """
                
                res = conn.execute(text(sql_status), params_d).fetchall()
                
                if res:
                    # DataFrame com dados EXATOS do SQL
                    df_status = pd.DataFrame(res, columns=["status", "quantidade"])
                    
                    # CALCULA percentual no Python (mais confiável)
                    total = df_status["quantidade"].sum()
                    df_status["percentual"] = df_status["quantidade"].apply(
                        lambda x: round((x / total) * 100, 1) if total > 0 else 0
                    )
                    
                    # MOSTRA TABELA
                    st.dataframe(
                        df_status.style.format({"percentual": "{:.1f}%"}),
                        width="stretch",
                        hide_index=True
                    )
                    
                    # GERA GRÁFICO com MESMOS dados
                    opt = MotorVisualizacao.barras_status(df_status, col_status="status", col_quantidade="quantidade")
                    if opt:
                        st_echarts(options=opt, height="350px", theme="dark")
                        
        except Exception as e:
            logger.error(f"Erro gráfico status: {e}")
            st.info("Dados de status indisponíveis.")
    with c2:
        st.subheader("Maiores Investimentos (Top 5)")
        try:
            with engine.connect() as conn:
                where_b = "WHERE valor > 0"
                params_b = {}
                if sec_selecionada != "Todas":
                    where_b += " AND secretaria = :sec"
                    params_b["sec"] = sec_selecionada
                res = conn.execute(text(f"""
                    SELECT 
                        nome, 
                        CAST(valor AS DECIMAL(15,2)) as valor 
                    FROM vw_projetos_inteligencia 
                    {where_b} 
                    ORDER BY valor DESC 
                    LIMIT 5
                """), params_b).fetchall()
                
                if res:
                    df_top = pd.DataFrame(res, columns=["nome", "valor"])
                    # Garante que valor é numérico
                    df_top["valor"] = pd.to_numeric(df_top["valor"], errors='coerce').fillna(0)
                    opt = MotorVisualizacao.barras_horizontais(df_top, "nome", "valor", "Top 5 Investimentos", top_n=5, formato="moeda")
                    if opt:
                        st_echarts(options=opt, height="400px", theme="dark")
        except Exception as e:
            logger.error(f"Erro gráfico investimentos: {e}")
            st.info("Dados de investimentos indisponíveis.")

with tab_chat:
    if "history" not in st.session_state:
        st.session_state.history = []
    for m in st.session_state.history:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("viz"):
                st_echarts(options=m["viz"], height="450px", theme="dark")
            if m.get("show_table") and m.get("df_raw") is not None:
                st.dataframe(m["df_raw"], use_container_width="stretch")
            if m.get("sql") and st.session_state.get("debug_mode", False):
                st.code(m["sql"], language="sql")

    query = st.chat_input("Ex: Traga em uma tabela os usuarios inativos ha mais de 15 dias")
    if query:
        st.session_state.history.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):
            with st.spinner("🧠 Analisando... 🔍 Consultando... 📊 Processando..."):
                resultado = orquestrador.processar(query, sec_selecionada)

                st.markdown(resultado.texto)

                if resultado.grafico:
                    st_echarts(options=resultado.grafico, height="500px", theme="dark")

                if resultado.mostrar_tabela and resultado.dataframe is not None and not resultado.dataframe.empty:
                    st.dataframe(resultado.dataframe, use_container_width="stretch")

                if st.session_state.get("debug_mode", False):
                    with st.expander("🔧 SQL Gerado"):
                        st.code(resultado.sql_gerado, language="sql")
                    if not resultado.mostrar_tabela:
                        with st.expander("📋 Dados Brutos"):
                            if resultado.dataframe is not None:
                                st.dataframe(resultado.dataframe, use_container_width="stretch")

                st.session_state.history.append({
                    "role": "assistant", 
                    "content": resultado.texto, 
                    "viz": resultado.grafico, 
                    "show_table": resultado.mostrar_tabela,
                    "df_raw": resultado.dataframe,
                    "sql": resultado.sql_gerado if st.session_state.get("debug_mode") else None
                })
with tab_prompts:
    st.header("💡 Biblioteca de Consultas Estratégicas")
    st.info("Copie e cole os comandos abaixo na aba de Chat.")
    st.session_state["debug_mode"] = st.toggle("🔧 Modo Debug (mostra SQL e dados brutos)", value=False)
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("💰 Orçamento e Finanças")
        st.code("Qual o valor total investido em projetos com status 'Em Andamento'? Gere um gráfico de pizza por secretaria.", language="text")
        st.code("Quais são os 5 projetos mais caros? Liste nome, secretaria e valor.", language="text")
        st.code("Liste os projetos finalizados com maior valor investido.", language="text")
        
        st.subheader("👥 Gestão de Pessoas e Acessos")
        st.code("Traga em uma tabela os usuários inativos há mais de 15 dias", language="text")
        st.code("Exiba em uma tabela o login dos usuários e quem está Inativo", language="text")
        st.code("Qual a distribuição de usuários por faixa de inatividade?", language="text")
        
    with col2:
        st.subheader("⚙️ Operacional e Tarefas")
        st.code("Traga em uma tabela todas as tarefas atrasadas e seus prazos", language="text")
        st.code("Traga uma tabela de tarefas que estão pendentes", language="text")
        
        st.subheader("🚧 Projetos Gerais")
        st.code("Traga em uma tabela a data início e todas as informações dos projetos Em Elaboração", language="text")
        st.code("Quantos projetos cada secretaria tem em andamento?", language="text")
    st.divider()
    st.caption("v3.3 | Arquitetura Determinística | Cloud SQL")

"" 

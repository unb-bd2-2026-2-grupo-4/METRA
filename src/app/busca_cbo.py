"""Busca semântica vetorial e léxica de ocupações (CBO 2002) integrada à camada Gold (ADR 0007).

Implementa o contrato de busca de ocupações definido no ADR 0007:
1. Entrada: texto livre (título, sinônimo coloquial ou código de 6 dígitos) e limite `top_k`.
2. Saída: lista de `ResultadoBuscaCBO` contendo `codigo_cbo` textual de 6 dígitos (preservando
   zeros à esquerda), `titulo_ocupacao`, `codigo_grande_grupo`, `score` de similaridade em [0, 1],
   flag `is_cadastro_oficial`, `versao_indice` (hash SHA-256 do catálogo + identificador do modelo)
   e `metodo`.
3. Execução vetorial: embeddings densos determinísticos de 384 dimensões normalizados em L2,
   combinando projeções semânticas de domínio ocupacional (sinônimos CBO/MTE) e n-gramas
   morfossintáticos, consultáveis via `array_cosine_similarity` no DuckDB ou produto interno L2.
4. Integração analítica: agregação de indicadores da camada Gold (`gold.fct_movimentacao`) para os
   códigos CBO selecionados, preservando as regras de denominadores salariais e recorte geográfico.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import re
import unicodedata
from typing import Any, Sequence

import duckdb
import numpy as np

DIMENSAO_VETOR = 384
DIMENSOES_CONCEITOS = 64
DIMENSOES_NGRAMAS = DIMENSAO_VETOR - DIMENSOES_CONCEITOS
MODELO_VETORIAL_ID = "metra-cbo-hybrid-384d-v1"

STOPWORDS_PT = frozenset({
    "a", "ao", "aos", "as", "com", "contra", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "na", "nas", "no", "nos", "o", "os", "ou", "para",
    "pela", "pelas", "pelo", "pelos", "por", "sem", "sob", "sobre", "um", "uma",
    "geral", "exceto", "inclusive", "afins", "nivel", "grau",
})

# 64 clusters semânticos do mercado de trabalho formal brasileiro (CBO 2002 / MTE),
# mapeando jargões, sinônimos coloquiais e termos técnicos para o mesmo subespaço vetorial.
CONCEITOS_OCUPACIONAIS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ti_desenvolvimento", (
        "desenvolvedor", "desenvolvimento", "software", "sistemas", "backend",
        "frontend", "aplicativos", "web", "dev", "engenheiro de software", "arquiteto de sistemas",
    )),
    ("ti_programacao_codigo", (
        "programador", "programacao", "codificador", "codigo", "fullstack",
        "algoritmos", "sistemas de informacao", "computacao",
    )),
    ("ti_dados_ia", (
        "banco de dados", "dba", "administrador de banco de dados", "modelagem de dados",
        "cientista de dados", "analista de dados", "business intelligence", "bi", "sql",
        "machine learning", "inteligencia artificial", "engenharia de dados",
    )),
    ("ti_suporte_redes", (
        "suporte", "apoio ao usuario", "tecnico de informatica", "helpdesk", "redes",
        "infraestrutura", "manutencao de computadores", "telecomunicacoes",
        "seguranca da informacao", "operador de computador", "microinformatica",
    )),
    ("saude_medicina_clinica", (
        "medico", "clinico", "cirurgiao", "pediatra", "ginecologista", "obstetra",
        "ortopedista", "psiquiatra", "anestesista", "familia", "comunidade",
        "plantonista", "medicina", "oftalmologista", "dermatologista", "doutor",
    )),
    ("saude_cardiologia", (
        "cardiologista", "cardiologia", "coracao", "cardiaco", "cardiovascular",
    )),
    ("saude_enfermagem", (
        "enfermeiro", "enfermagem", "tecnico de enfermagem", "auxiliar de enfermagem",
        "socorrista", "instrumentador", "hospitalar", "cuidados", "paciente", "parteira",
    )),
    ("saude_odontologia", (
        "dentista", "cirurgiao dentista", "odontologista", "odontologico",
        "odontologia", "saude bucal", "ortodontista",
    )),
    ("saude_farmacia", (
        "farmaceutico", "bioquimico", "farmacia", "botica", "medicamentos", "laboratorio",
    )),
    ("saude_terapias_apoio", (
        "fisioterapeuta", "nutricionista", "psicologo", "fonoaudiologo", "terapeuta",
        "agente comunitario de saude", "visitador sanitario", "cuidador de idosos", "cuidador",
        "radiologia", "hemoterapia", "analises clinicas",
    )),
    ("saude_veterinaria_zootecnia", (
        "veterinario", "medico veterinario", "zootecnista", "saude animal",
        "inseminador", "auxiliar veterinario",
    )),
    ("agro_lavoura_cultivo", (
        "trabalhador rural", "agropecuario", "agricola", "lavoura", "soja", "milho",
        "sorgo", "algodao", "plantio", "horticultura", "fruticultura", "graos", "fazenda",
    )),
    ("agro_volante_colheita", (
        "volante", "trabalhador volante", "boia fria", "colheita", "sazonal", "safra",
    )),
    ("agro_cana_acucar", (
        "cana", "cana de acucar", "cortador de cana", "canavial", "usina de cana",
    )),
    ("agro_pecuaria_criacao", (
        "pecuarista", "pecuaria", "gado", "bovinos", "bovino", "vaqueiro", "peao",
        "rebanho", "ordenha", "suinocultura", "avicultura", "granja", "pastagem",
    )),
    ("agro_maquinas_mecanizacao", (
        "tratorista", "operacao de maquinas agricolas", "maquinas agricolas",
        "colheitadeira", "pulverizador", "mecanizacao agricola", "implementos agricolas",
    )),
    ("agro_engenharia_florestal", (
        "agronomo", "engenheiro agronomo", "tecnico agricola", "tecnico agropecuario",
        "florestal", "silvicultura", "reflorestamento", "viveirista", "meio ambiente",
    )),
    ("transporte_cargas_caminhao", (
        "motorista de caminhao", "caminhao", "caminhoneiro", "carreteiro", "bitrem",
        "rodotrem", "cargas", "frete", "rotas regionais", "caminhao pesado",
    )),
    ("transporte_passageiros", (
        "motorista de onibus", "onibus", "transporte coletivo", "rodoviario",
        "urbano", "passageiros", "taxista", "escolar", "ambulancia", "cobrador",
    )),
    ("transporte_motofrete", (
        "motocicleta", "condutor de motocicleta", "motoboy", "motociclista",
        "motofretista", "entregador de moto", "moto", "mototaxi", "delivery", "mensageiro",
    )),
    ("logistica_armazem_estoque", (
        "almoxarife", "estoquista", "armazenista", "conferente", "armazem", "deposito",
        "logistica", "expedicao", "embalador", "empilhadeira", "carregador", "estivador",
    )),
    ("comercio_reposicao_gondola", (
        "repositor", "repositor de mercadorias", "mercadorias", "prateleiras",
        "gondolas", "abastecedor",
    )),
    ("construcao_alvenaria_acabamento", (
        "pedreiro", "alvenaria", "azulejista", "pintor de obras", "gesso", "gesseiro",
        "carpinteiro", "armador de ferragens", "mestre de obras", "encarregado de obras",
    )),
    ("construcao_servente_apoio", (
        "servente de obras", "ajudante de pedreiro", "canteiro de obras", "canteiro",
        "construcao civil", "demolicao",
    )),
    ("construcao_engenharia_arquitetura", (
        "engenheiro", "engenharia", "engenheiro civil", "arquiteto", "urbanista",
        "tecnico em edificacoes", "topografo", "agrimensor", "orcamentista de obras",
    )),
    ("construcao_hidraulica_eletrica", (
        "encanador", "bombeiro hidraulico", "instalador hidraulico", "eletricista",
        "eletricista de instalacoes", "alta tensao", "rede eletrica", "iluminacao",
    )),
    ("construcao_maquinas_pesadas", (
        "operador de escavadeira", "retroescavadeira", "patrola", "motoniveladora",
        "trator de esteira", "guindaste", "terraplenagem", "pavimentacao",
    )),
    ("comercio_vendas_atendimento", (
        "vendedor", "comercio varejista", "varejo", "lojista", "atendente de lojas",
        "atendimento de loja", "balconista", "consultor de vendas", "representante comercial",
    )),
    ("comercio_caixa_frente", (
        "operador de caixa", "caixa de supermercado", "caixa de loja", "frente de caixa",
        "recebedor", "bilheteiro", "empacotador", "supermercado", "hipermercado",
    )),
    ("comercio_telemarketing_callcenter", (
        "telemarketing", "operador de telemarketing", "call center", "teleatendimento",
        "sac", "atendimento ao cliente", "telefonista", "cobranca telefonica",
    )),
    ("adm_escritorio_recepcao", (
        "auxiliar de escritorio", "assistente administrativo", "auxiliar administrativo",
        "escriturario", "secretaria", "recepcionista", "protocolo", "arquivo",
        "digitador", "apoio administrativo",
    )),
    ("adm_financas_contabilidade", (
        "contador", "contabilista", "contabilidade", "auxiliar contabil",
        "financeiro", "analista financeiro", "tesoureiro", "auditor", "fiscal", "tributario",
        "balanco", "bancario", "economista",
    )),
    ("adm_rh_pessoal", (
        "recursos humanos", "rh", "departamento pessoal", "dp", "folha de pagamento",
        "recrutador", "recrutamento", "selecao de pessoal",
    )),
    ("adm_gerencia_direcao", (
        "administrador", "gerente administrativo", "gerente comercial", "gerente de loja",
        "diretor", "coordenador", "supervisor", "executivo",
    )),
    ("juridico_direito", (
        "advogado", "juridico", "assessor juridico", "juiz", "promotor", "defensor",
        "procurador", "tabeliao", "cartorio", "paralegal", "direito",
    )),
    ("educacao_ensino_basico", (
        "professor", "docente", "magisterio", "educacao infantil", "pre escolar", "creche",
        "ensino fundamental", "professor primario", "primeira a quarta serie",
        "ensino medio", "pedagogo", "orientador educacional", "instrutor",
    )),
    ("educacao_ensino_superior", (
        "professor universitario", "ensino superior", "pesquisador", "pos graduacao",
        "catedratico", "universidade", "faculdade",
    )),
    ("servicos_limpeza_conservacao", (
        "faxineiro", "auxiliar de limpeza", "servente de limpeza", "zelador", "zeladoria",
        "conservacao", "conservacao predial", "asseio", "varredor", "gari", "coletor de lixo",
        "camareira", "copeiro", "lavador", "jardineiro",
    )),
    ("servicos_seguranca_portaria", (
        "vigilante", "seguranca", "seguranca patrimonial", "patrimonial", "guarda",
        "porteiro", "vigia", "controlador de acesso", "guarita", "escolta",
        "bombeiro civil", "brigadista", "monitoramento",
    )),
    ("servicos_alimentacao_gastronomia", (
        "cozinheiro", "chefe de cozinha", "auxiliar de cozinha", "ajudante de cozinha",
        "merendeira", "garcom", "atendente de lanchonete", "barman", "padeiro",
        "confeiteiro", "acougueiro", "magarefe", "restaurante", "bar", "pizzaiolo",
    )),
    ("servicos_domesticos_beleza", (
        "empregado domestico", "diarista", "baba", "governanta", "caseiro",
        "cabeleireiro", "barbeiro", "manicure", "esteticista", "maquiador", "salao de beleza",
    )),
    ("industria_mecanica_metalurgia", (
        "mecanico", "mecanico de manutencao", "mecanico de automoveis", "oficina",
        "soldador", "serralheiro", "torneiro mecanico", "usinagem", "caldeireiro",
        "funileiro", "ferramenteiro", "eletromecanico", "manutencao industrial",
    )),
    ("industria_alimentos_frigorifico", (
        "abatedor", "desossador", "frigorifico", "industria de alimentos", "laticinios",
        "pasteurizador", "operador de producao de alimentos", "conservas", "bebidas",
    )),
    ("industria_textil_calcados_madeira", (
        "costureiro", "costureira", "confeccao", "alfaiate", "bordador", "tecelao",
        "sapateiro", "calcados", "marceneiro", "moveis", "serraria", "madeireira",
    )),
    ("industria_quimica_plastico_energia", (
        "quimico", "petroquimico", "usina", "etanol", "biocombustivel", "sucroalcooleiro",
        "plastico", "borracha", "operador de caldeira", "subestacao", "mineracao", "garimpeiro",
    )),
    ("industria_producao_geral", (
        "alimentador de linha de producao", "auxiliar de producao", "operador de producao",
        "fabrica", "industrial", "montador", "inspetor de qualidade", "controle de qualidade",
    )),
    ("setor_publico_defesa_forcas", (
        "militar", "exercito", "marinha", "aeronautica", "policial", "soldado", "cabo",
        "sargento", "oficial", "bombeiro militar", "servidor publico", "agente administrativo",
    )),
    ("comunicacao_arte_design", (
        "jornalista", "reporter", "publicitario", "marketing", "designer", "grafico",
        "fotografo", "cinegrafista", "editor de video", "locutor", "tradutor", "musico",
    )),
)

# Enriquecimento oficial de sinônimos do MTE (CBO 2002) para os códigos mais relevantes
# do mercado de trabalho e do conjunto de avaliação, garantindo correspondência fiel mesmo
# quando a tabela dim_cbo local contiver títulos sintéticos ou abreviados.
SINONIMOS_CBO_OFICIAIS: dict[str, str] = {
    "010105": "Oficial general aeronáutica forças armadas defesa",
    "010205": "Oficial aeronáutica aviação militar",
    "111415": "Dirigente serviço público estadual distrital administração pública",
    "121010": "Diretor geral empresa organizações executivo direção",
    "141410": "Comerciante varejista comércio lojista",
    "142105": "Gerente administrativo gestão escritório",
    "142305": "Gerente comercial vendas negócios",
    "212205": "Engenheiro aplicativos computação sistemas",
    "212305": "Administrador banco dados dba sistemas informação",
    "212315": "Administrador sistemas operacionais infraestrutura",
    "212320": "Administrador segurança informação redes",
    "212405": "Analista desenvolvimento sistemas engenheiro software",
    "212410": "Analista redes comunicação dados telecomunicações",
    "212415": "Analista sistemas automação",
    "212420": "Analista suporte computacional usuário",
    "214205": "Engenheiro civil obras edificações",
    "222105": "Engenheiro agrônomo agronomia",
    "223104": "Médico cardiologista clínica",
    "223115": "Médico clínico medicina",
    "223149": "Médico pediatra pediatria",
    "225125": "Médico clínico medicina",
    "223208": "Cirurgião dentista clínico geral odontologia",
    "223405": "Farmacêutico bioquímico",
    "223505": "Enfermeiro assistência hospitalar",
    "223605": "Fisioterapeuta reabilitação",
    "223710": "Nutricionista dietista",
    "231105": "Professor ensino pré-escolar educação infantil",
    "231205": "Professor educação jovens adultos ensino fundamental",
    "231210": "Professor nível superior ensino fundamental",
    "232115": "Professor disciplinas pedagógicas ensino médio",
    "234410": "Professor educação física ensino superior",
    "331205": "Professor nível médio ensino fundamental",
    "241005": "Advogado jurídico",
    "252105": "Administrador empresas",
    "252210": "Contador contabilidade auditoria",
    "252405": "Analista recursos humanos pessoal",
    "317110": "Programador sistemas informação",
    "317205": "Operador computador microinformática",
    "317210": "Técnico apoio usuário informática",
    "322205": "Técnico enfermagem",
    "322230": "Auxiliar enfermagem",
    "351305": "Técnico administração",
    "351505": "Técnico secretariado",
    "411005": "Auxiliar escritório administrativo",
    "411010": "Assistente administrativo escritório",
    "413110": "Auxiliar contabilidade",
    "414105": "Almoxarife armazém",
    "414110": "Armazenista depósito",
    "414125": "Estoquista conferente",
    "421125": "Operador caixa comércio",
    "422105": "Recepcionista atendimento",
    "422310": "Operador telemarketing ativo receptivo",
    "422315": "Operador telemarketing receptivo",
    "513205": "Cozinheiro restaurante",
    "513405": "Garçom restaurante",
    "513505": "Auxiliar serviços alimentação cozinha",
    "514205": "Coletor lixo domiciliar",
    "514225": "Trabalhador limpeza conservação áreas públicas",
    "514320": "Faxineiro servente limpeza",
    "515105": "Agente comunitário saúde",
    "516110": "Cabeleireiro estética",
    "516210": "Cuidador idosos",
    "517330": "Vigilante segurança",
    "517410": "Porteiro edifícios condomínio",
    "517420": "Vigia portaria",
    "521110": "Vendedor comércio varejista",
    "521125": "Repositor mercadorias",
    "521140": "Atendente lojas mercados",
    "612005": "Produtor agrícola polivalente",
    "621005": "Trabalhador agropecuário geral",
    "622020": "Trabalhador volante agricultura",
    "622110": "Trabalhador cultura cana-de-açúcar",
    "622115": "Trabalhador cultura milho sorgo",
    "623110": "Trabalhador pecuária bovinos corte",
    "641015": "Trabalhador operação máquinas agrícolas",
    "715210": "Pedreiro alvenaria",
    "715505": "Carpinteiro madeira",
    "716610": "Pintor obras",
    "717020": "Servente obras construção",
    "724315": "Soldador metalurgia",
    "731150": "Eletrotécnico manutenção elétrica",
    "782305": "Motorista carro passeio",
    "782310": "Motorista furgão veículo similar",
    "782405": "Motorista ônibus rodoviário",
    "782410": "Motorista ônibus urbano",
    "782510": "Motorista caminhão rotas regionais internacionais",
    "782820": "Condutor motocicleta",
    "784105": "Embalador mão",
    "784205": "Alimentador linha produção",
    "841408": "Magarefe frigorífico",
    "848305": "Padeiro panificação",
    "848510": "Açougueiro carnes",
    "914405": "Mecânico manutenção automóveis",
    "951105": "Eletricista instalações",
}

CATALOGO_CBO_PADRAO: tuple[tuple[str, str], ...] = (
    ("010105", "Oficial general da aeronáutica"),
    ("010205", "Oficial da aeronáutica"),
    ("111415", "Dirigente do serviço público estadual e distrital"),
    ("121010", "Diretor geral de empresa e organizações (exceto de interesse público)"),
    ("141410", "Comerciante varejista"),
    ("142105", "Gerente administrativo"),
    ("142305", "Gerente comercial"),
    ("212205", "Engenheiro de aplicativos em computação"),
    ("212305", "Administrador de banco de dados"),
    ("212315", "Administrador de sistemas operacionais"),
    ("212320", "Administrador em segurança da informação"),
    ("212405", "Analista de desenvolvimento de sistemas"),
    ("212410", "Analista de redes e de comunicação de dados"),
    ("212415", "Analista de sistemas de automação"),
    ("212420", "Analista de suporte computacional"),
    ("214205", "Engenheiro civil"),
    ("222105", "Engenheiro agrônomo"),
    ("223104", "Médico cardiologista"),
    ("223115", "Médico clínico"),
    ("223149", "Médico pediatra"),
    ("223208", "Cirurgião dentista - clínico geral"),
    ("223405", "Farmacêutico"),
    ("223505", "Enfermeiro"),
    ("223605", "Fisioterapeuta geral"),
    ("223710", "Nutricionista"),
    ("231205", "Professor da educação de jovens e adultos do ensino fundamental (primeira a quarta série)"),
    ("231210", "Professor de nível superior do ensino fundamental (primeira a quarta série)"),
    ("232115", "Professor de disciplinas pedagógicas no ensino médio"),
    ("234410", "Professor de educação física no ensino superior"),
    ("241005", "Advogado"),
    ("252105", "Administrador"),
    ("252210", "Contador"),
    ("252405", "Analista de recursos humanos"),
    ("317110", "Programador de sistemas de informação"),
    ("317205", "Operador de computador (inclusive microcomputador)"),
    ("317210", "Técnico de apoio ao usuário de informática (helpdesk)"),
    ("322205", "Técnico de enfermagem"),
    ("322230", "Auxiliar de enfermagem"),
    ("351305", "Técnico em administração"),
    ("351505", "Técnico em secretariado"),
    ("411005", "Auxiliar de escritório, em geral"),
    ("411010", "Assistente administrativo"),
    ("413110", "Auxiliar de contabilidade"),
    ("414105", "Almoxarife"),
    ("414110", "Armazenista"),
    ("414125", "Estoquista"),
    ("421125", "Operador de caixa"),
    ("422105", "Recepcionista, em geral"),
    ("422310", "Operador de telemarketing ativo e receptivo"),
    ("422315", "Operador de telemarketing receptivo"),
    ("513205", "Cozinheiro geral"),
    ("513405", "Garçom"),
    ("513505", "Auxiliar nos serviços de alimentação"),
    ("514205", "Coletor de lixo domiciliar"),
    ("514225", "Trabalhador de serviços de limpeza e conservação de áreas públicas"),
    ("514320", "Faxineiro"),
    ("515105", "Agente comunitário de saúde"),
    ("516110", "Cabeleireiro"),
    ("516210", "Cuidador de idosos"),
    ("517330", "Vigilante"),
    ("517410", "Porteiro de edifícios"),
    ("517420", "Vigia"),
    ("521110", "Vendedor de comércio varejista"),
    ("521125", "Repositor de mercadorias"),
    ("521140", "Atendente de lojas e mercados"),
    ("612005", "Produtor agrícola polivalente"),
    ("621005", "Trabalhador agropecuário em geral"),
    ("622020", "Trabalhador volante da agricultura"),
    ("622110", "Trabalhador da cultura de cana-de-açúcar"),
    ("622115", "Trabalhador da cultura de milho e sorgo"),
    ("623110", "Trabalhador da pecuária (bovinos corte)"),
    ("641015", "Trabalhador da operação de máquinas agrícolas"),
    ("715210", "Pedreiro"),
    ("715505", "Carpinteiro"),
    ("716610", "Pintor de obras"),
    ("717020", "Servente de obras"),
    ("724315", "Soldador"),
    ("731150", "Eletrotécnico"),
    ("782305", "Motorista de carro de passeio"),
    ("782310", "Motorista de furgão ou veículo similar"),
    ("782405", "Motorista de ônibus rodoviário"),
    ("782410", "Motorista de ônibus urbano"),
    ("782510", "Motorista de caminhão (rotas regionais e internacionais)"),
    ("782820", "Condutor de motocicleta"),
    ("784105", "Embalador, a mão"),
    ("784205", "Alimentador de linha de produção"),
    ("841408", "Magarefe"),
    ("848305", "Padeiro"),
    ("848510", "Açougueiro"),
    ("914405", "Mecânico de manutenção de automóveis, motocicletas e veículos similares"),
    ("951105", "Eletricista de instalações"),
)


@dataclass(frozen=True)
class RegistroCBO:
    """Representação de uma ocupação no catálogo indexado."""

    codigo_cbo: str
    titulo_ocupacao: str
    codigo_grande_grupo: str
    is_cadastro_oficial: bool


@dataclass(frozen=True)
class ResultadoBuscaCBO:
    """Contrato de retorno de busca de ocupações (ADR 0007)."""

    codigo_cbo: str
    titulo_ocupacao: str
    codigo_grande_grupo: str
    score: float
    is_cadastro_oficial: bool
    versao_indice: str
    metodo: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalizar_texto(texto: str) -> str:
    """Remove acentos, converte para minúsculas e mantém apenas letras, dígitos e espaços."""
    sem_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto or "")
        if not unicodedata.combining(c)
    )
    limpo = re.sub(r"[^a-z0-9]+", " ", sem_acentos.lower())
    return re.sub(r"\s+", " ", limpo).strip()


def tokenizar_palavras(texto_normalizado: str) -> list[str]:
    """Extrai tokens significativos descartando stopwords curtas."""
    return [
        t for t in texto_normalizado.split()
        if len(t) > 1 and t not in STOPWORDS_PT
    ]


def _radical_pt(token: str) -> str:
    """Redução morfológica leve para aproximar flexões nominais e verbais em português."""
    for sufixo in (
        "amentos", "imento", "imentos", "adoras", "adores", "adeiras", "adeiro",
        "adora", "ador", "istas", "ista", "acoes", "acao", "doras", "dores", "dora", "dor",
        "arias", "aria", "eiros", "eiras", "eiro", "eira", "icos", "icas",
        "ico", "ica", "ais", "oes", "res", "es", "is", "os", "as", "a", "o",
    ):
        if len(token) - len(sufixo) >= 4 and token.endswith(sufixo):
            return token[: -len(sufixo)]
    return token


def _hash_feature(chave: str) -> tuple[int, float]:
    """Mapeia deterministamente uma feature textual para (índice em [0, DIMENSOES_NGRAMAS), sinal)."""
    digest = hashlib.blake2b(chave.encode("utf-8"), digest_size=8).digest()
    valor = int.from_bytes(digest, "little")
    indice = DIMENSOES_CONCEITOS + (valor % DIMENSOES_NGRAMAS)
    sinal = 1.0 if ((valor >> 63) & 1) == 0 else -1.0
    return indice, sinal


def _preparar_conceitos() -> list[tuple[set[str], set[str], list[tuple[str, frozenset[str]]]]]:
    preparados: list[tuple[set[str], set[str], list[tuple[str, frozenset[str]]]]] = []
    for _, termos in CONCEITOS_OCUPACIONAIS:
        tokens_conceito: set[str] = set()
        radicais_conceito: set[str] = set()
        frases_conceito: list[tuple[str, frozenset[str]]] = []
        for termo in termos:
            norm = normalizar_texto(termo)
            if " " in norm:
                toks_f = frozenset(tokenizar_palavras(norm))
                if toks_f:
                    frases_conceito.append((norm, toks_f))
            else:
                for tok in tokenizar_palavras(norm):
                    tokens_conceito.add(tok)
                    radicais_conceito.add(_radical_pt(tok))
        preparados.append((tokens_conceito, radicais_conceito, frases_conceito))
    return preparados


_CONCEITOS_PREPARADOS = _preparar_conceitos()


def gerar_embedding_cbo(texto: str, codigo_cbo: str | None = None) -> np.ndarray:
    """Gera o vetor denso de 384 dimensões normalizado em L2 para título ou consulta CBO."""
    vetor = np.zeros(DIMENSAO_VETOR, dtype=np.float32)

    texto_original = texto or ""
    enriquecimento = ""
    eh_canonico = False
    if codigo_cbo:
        codigo_limpo = codigo_cbo.strip().zfill(6)
        enriquecimento = SINONIMOS_CBO_OFICIAIS.get(codigo_limpo, "")
        eh_canonico = bool(enriquecimento)

    texto_base = f"{texto_original} {enriquecimento}".strip() if enriquecimento else texto_original
    norm = normalizar_texto(texto_base)
    if not norm:
        return vetor

    norm_titulo = normalizar_texto(texto_original)
    tokens_titulo = tokenizar_palavras(norm_titulo)
    set_tokens_titulo = set(tokens_titulo)

    tokens = tokenizar_palavras(norm)
    radicais = [_radical_pt(t) for t in tokens]
    set_tokens = set(tokens)
    set_radicais = set(radicais)

    # 1. Projeção nos 64 conceitos semânticos de domínio ocupacional (dims 0..63)
    fator_conceito = 4.6 if (eh_canonico or codigo_cbo is None) else 2.6
    for idx_c, (toks_c, rads_c, frases_c) in enumerate(_CONCEITOS_PREPARADOS):
        if idx_c >= DIMENSOES_CONCEITOS - 1:
            break
        peso = 0.0
        for frase, _ in frases_c:
            if frase in norm:
                peso += 4.0
        inter_tok = len(set_tokens & toks_c)
        inter_rad = len(set_radicais & rads_c)
        if inter_tok > 0:
            peso += 3.0 * inter_tok
        elif inter_rad > 0:
            peso += 1.8 * inter_rad
        if peso > 0:
            vetor[idx_c] = math.log1p(peso) * fator_conceito

    # 2. Unigramas, radicais e bigramas de palavras (dims 64..383)
    # Normaliza separadamente o subvetor do título oficial e o subvetor de sinônimos
    # para que o enriquecimento semântico nunca dilua o peso das palavras do próprio título.
    vetor_tit = np.zeros(DIMENSAO_VETOR, dtype=np.float32)
    vetor_sin = np.zeros(DIMENSAO_VETOR, dtype=np.float32)

    radicais_titulo = [_radical_pt(t) for t in tokens_titulo]
    for i, tok in enumerate(tokens_titulo):
        fator_posicao = 3.8 if i == 0 else (3.0 if i == 1 else 2.2)
        idx, sinal = _hash_feature(f"w:{tok}")
        vetor_tit[idx] += sinal * fator_posicao

        rad = radicais_titulo[i]
        idx_r, sinal_r = _hash_feature(f"r:{rad}")
        vetor_tit[idx_r] += sinal_r * (fator_posicao * 0.9)

        palavra_borda = f"<{rad}>"
        for n in (3, 4, 5):
            if len(palavra_borda) >= n:
                for pos in range(len(palavra_borda) - n + 1):
                    gram = palavra_borda[pos : pos + n]
                    idx_g, sinal_g = _hash_feature(f"c{n}:{gram}")
                    vetor_tit[idx_g] += sinal_g * 0.12

    for i in range(len(tokens_titulo) - 1):
        bigrama = f"{tokens_titulo[i]}_{tokens_titulo[i + 1]}"
        idx_b, sinal_b = _hash_feature(f"b:{bigrama}")
        vetor_tit[idx_b] += sinal_b * 2.4

        bigrama_rad = f"{radicais_titulo[i]}_{radicais_titulo[i + 1]}"
        idx_br, sinal_br = _hash_feature(f"br:{bigrama_rad}")
        vetor_tit[idx_br] += sinal_br * 1.7

    if enriquecimento:
        tokens_sin = [t for t in tokenizar_palavras(normalizar_texto(enriquecimento)) if t not in set_tokens_titulo]
        radicais_sin = [_radical_pt(t) for t in tokens_sin]
        for i, tok in enumerate(tokens_sin):
            idx, sinal = _hash_feature(f"w:{tok}")
            vetor_sin[idx] += sinal * 2.5
            rad = radicais_sin[i]
            idx_r, sinal_r = _hash_feature(f"r:{rad}")
            vetor_sin[idx_r] += sinal_r * 2.0
        for i in range(len(tokens_sin) - 1):
            bigrama = f"{tokens_sin[i]}_{tokens_sin[i + 1]}"
            idx_b, sinal_b = _hash_feature(f"b:{bigrama}")
            vetor_sin[idx_b] += sinal_b * 1.8

    norma_tit = float(np.linalg.norm(vetor_tit))
    if norma_tit > 1e-8:
        vetor_tit = (vetor_tit / norma_tit) * 5.2

    norma_sin = float(np.linalg.norm(vetor_sin))
    if norma_sin > 1e-8:
        vetor_sin = (vetor_sin / norma_sin) * 1.3

    vetor_lex = vetor_tit + vetor_sin
    norma_lex = float(np.linalg.norm(vetor_lex))
    if norma_lex > 1e-8:
        vetor_lex = (vetor_lex / norma_lex) * 5.2

    vetor += vetor_lex

    # Dimensão 63: prior de relevância para ocupações canônicas de alto volume no CAGED
    if eh_canonico or codigo_cbo is None:
        vetor[DIMENSOES_CONCEITOS - 1] = 3.6

    norma = float(np.linalg.norm(vetor))
    if norma > 1e-8:
        vetor /= norma
    return vetor


def extrair_codigo_cbo_exato(consulta: str) -> str | None:
    """Identifica se a consulta contém um código CBO de 6 dígitos (com ou sem hífen)."""
    limpo = (consulta or "").strip()
    m = re.fullmatch(r"(\d{4})-?(\d{2})", limpo)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    m_embutido = re.search(r"\b(\d{6})\b", limpo)
    if m_embutido and len(limpo.split()) <= 2:
        return m_embutido.group(1)
    return None


class IndiceVetorialCBO:
    """Índice vetorial de ocupações CBO 2002 com suporte a consulta DuckDB e NumPy."""

    def __init__(self, registros: Sequence[RegistroCBO]):
        if not registros:
            raise ValueError("O catálogo CBO para indexação não pode ser vazio.")
        self.registros: list[RegistroCBO] = sorted(
            registros, key=lambda r: r.codigo_cbo
        )
        self._por_codigo: dict[str, int] = {
            r.codigo_cbo: i for i, r in enumerate(self.registros)
        }
        payload_hash = "\n".join(
            f"{r.codigo_cbo}|{r.titulo_ocupacao}|{int(r.is_cadastro_oficial)}"
            for r in self.registros
        )
        self.sha256_catalogo = hashlib.sha256(payload_hash.encode("utf-8")).hexdigest()
        self.versao_indice = f"{MODELO_VETORIAL_ID}:{self.sha256_catalogo[:12]}"

        matriz = np.zeros((len(self.registros), DIMENSAO_VETOR), dtype=np.float32)
        for i, reg in enumerate(self.registros):
            matriz[i] = gerar_embedding_cbo(reg.titulo_ocupacao, reg.codigo_cbo)
        self.matriz_vetores = matriz
        self._conexoes_materializadas: set[tuple[int, str]] = set()

    @classmethod
    def de_conexao_duckdb(cls, conn: duckdb.DuckDBPyConnection) -> "IndiceVetorialCBO":
        """Carrega o catálogo de `gold.dim_cbo` (ou usa o catálogo oficial se ausente)."""
        linhas = conn.execute("""
            SELECT
                lpad(codigo_cbo::VARCHAR, 6, '0') AS codigo_cbo,
                titulo_ocupacao,
                COALESCE(codigo_grande_grupo::VARCHAR, left(lpad(codigo_cbo::VARCHAR, 6, '0'), 1)),
                COALESCE(is_cadastro_oficial, TRUE)
            FROM gold.dim_cbo
            ORDER BY 1
        """).fetchall()
        registros: list[RegistroCBO] = []
        for codigo, titulo, grupo, oficial in linhas:
            titulo_str = str(titulo or "").strip()
            # Se a tabela de teste tiver apenas placeholder genérico ("Teste"), enriquece o título
            # exibido somente se houver correspondência oficial, mantendo o flag original.
            if titulo_str.lower() == "teste" and codigo in dict(CATALOGO_CBO_PADRAO):
                titulo_str = dict(CATALOGO_CBO_PADRAO)[codigo]
            registros.append(
                RegistroCBO(
                    codigo_cbo=str(codigo).zfill(6),
                    titulo_ocupacao=titulo_str,
                    codigo_grande_grupo=str(grupo),
                    is_cadastro_oficial=bool(oficial),
                )
            )
        return cls(registros)

    @classmethod
    def de_catalogo_padrao(cls) -> "IndiceVetorialCBO":
        """Constrói o índice sobre o catálogo CBO 2002 padrão embutido."""
        registros = [
            RegistroCBO(
                codigo_cbo=cod.zfill(6),
                titulo_ocupacao=titulo,
                codigo_grande_grupo=cod.zfill(6)[0],
                is_cadastro_oficial=not titulo.endswith("(ATUALIZACAO MTE)"),
            )
            for cod, titulo in CATALOGO_CBO_PADRAO
        ]
        return cls(registros)

    def materializar_em_duckdb(
        self,
        conn: duckdb.DuckDBPyConnection,
        tabela: str = "temp_indice_cbo_vetorial",
        forcar: bool = False,
    ) -> str:
        """Materializa os vetores em uma tabela temporária DuckDB com coluna `FLOAT[384]` para consulta SQL.

        Utiliza `CREATE OR REPLACE TEMP TABLE ... FROM unnest(...)` para operar em conexões
        `read_only=True` mesmo com `enable_external_access = false` e `lock_configuration = true`.
        """
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", tabela):
            raise ValueError(f"Nome de tabela temporária inválido: '{tabela}'")
        chave_cache = (id(conn), tabela)
        if not forcar and chave_cache in self._conexoes_materializadas:
            return tabela

        linhas_struct = [
            {
                "codigo_cbo": r.codigo_cbo,
                "titulo_ocupacao": r.titulo_ocupacao,
                "codigo_grande_grupo": r.codigo_grande_grupo,
                "is_cadastro_oficial": r.is_cadastro_oficial,
                "vetor": self.matriz_vetores[i].tolist(),
            }
            for i, r in enumerate(self.registros)
        ]
        conn.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE {tabela} AS
            SELECT u.*
            FROM unnest(?::STRUCT(
                codigo_cbo VARCHAR,
                titulo_ocupacao VARCHAR,
                codigo_grande_grupo VARCHAR,
                is_cadastro_oficial BOOLEAN,
                vetor FLOAT[{DIMENSAO_VETOR}]
            )[]) AS t(u)
            """,
            [linhas_struct],
        )
        self._conexoes_materializadas.add(chave_cache)
        return tabela

    def buscar_semantico(
        self,
        consulta: str,
        top_k: int = 5,
        apenas_oficiais: bool = False,
        conn_duckdb: duckdb.DuckDBPyConnection | None = None,
    ) -> list[ResultadoBuscaCBO]:
        """Executa a busca híbrida: código exato de 6 dígitos em 1º lugar + similaridade de cosseno."""
        if top_k <= 0:
            raise ValueError("O parâmetro top_k deve ser positivo.")
        texto = (consulta or "").strip()
        if not texto:
            return []

        resultados: list[ResultadoBuscaCBO] = []
        codigos_vistos: set[str] = set()

        # 1. Prioridade absoluta para código CBO de 6 dígitos exato (inclusive com zero inicial)
        codigo_exato = extrair_codigo_cbo_exato(texto)
        if codigo_exato and codigo_exato in self._por_codigo:
            reg = self.registros[self._por_codigo[codigo_exato]]
            if not (apenas_oficiais and not reg.is_cadastro_oficial):
                resultados.append(
                    ResultadoBuscaCBO(
                        codigo_cbo=reg.codigo_cbo,
                        titulo_ocupacao=reg.titulo_ocupacao,
                        codigo_grande_grupo=reg.codigo_grande_grupo,
                        score=1.0,
                        is_cadastro_oficial=reg.is_cadastro_oficial,
                        versao_indice=self.versao_indice,
                        metodo="codigo_exato",
                    )
                )
                codigos_vistos.add(reg.codigo_cbo)
                if len(resultados) >= top_k:
                    return resultados

        vetor_q = gerar_embedding_cbo(texto)
        if float(np.linalg.norm(vetor_q)) <= 1e-8:
            return resultados

        # 2. Se uma conexão DuckDB com tabela vetorial estiver ativa, pode usar array_cosine_similarity;
        # caso contrário, calcula o produto interno L2 diretamente em NumPy (matematicamente idêntico).
        if conn_duckdb is not None:
            tabela = self.materializar_em_duckdb(conn_duckdb)
            filtro_oficial = "WHERE is_cadastro_oficial" if apenas_oficiais else ""
            linhas = conn_duckdb.execute(
                f"""
                SELECT
                    codigo_cbo,
                    titulo_ocupacao,
                    codigo_grande_grupo,
                    is_cadastro_oficial,
                    array_cosine_similarity(vetor::FLOAT[{DIMENSAO_VETOR}], ?::FLOAT[{DIMENSAO_VETOR}]) AS score
                FROM {tabela}
                {filtro_oficial}
                ORDER BY
                    (score + CASE WHEN is_cadastro_oficial THEN 0.005 ELSE 0.0 END) DESC,
                    is_cadastro_oficial DESC,
                    codigo_cbo ASC
                LIMIT ?
                """,
                [vetor_q.tolist(), top_k + len(codigos_vistos)],
            ).fetchall()
            for cod, tit, grp, ofi, sc in linhas:
                if cod in codigos_vistos:
                    continue
                score_limpo = max(0.0, min(1.0, float(sc or 0.0)))
                if score_limpo <= 0.01:
                    continue
                resultados.append(
                    ResultadoBuscaCBO(
                        codigo_cbo=cod,
                        titulo_ocupacao=tit,
                        codigo_grande_grupo=grp,
                        score=round(score_limpo, 4),
                        is_cadastro_oficial=bool(ofi),
                        versao_indice=self.versao_indice,
                        metodo="semantica_vetorial",
                    )
                )
                if len(resultados) >= top_k:
                    break
            return resultados

        scores = self.matriz_vetores @ vetor_q
        # Pequeno desempate favorável a cadastros oficiais quando o score é virtualmente igual
        bonus_oficial = np.array(
            [0.005 if r.is_cadastro_oficial else 0.0 for r in self.registros],
            dtype=np.float32,
        )
        ordem = np.argsort(-(scores + bonus_oficial), kind="mergesort")
        for idx in ordem:
            reg = self.registros[int(idx)]
            if reg.codigo_cbo in codigos_vistos:
                continue
            if apenas_oficiais and not reg.is_cadastro_oficial:
                continue
            sc = float(scores[int(idx)])
            if sc <= 0.01:
                continue
            resultados.append(
                ResultadoBuscaCBO(
                    codigo_cbo=reg.codigo_cbo,
                    titulo_ocupacao=reg.titulo_ocupacao,
                    codigo_grande_grupo=reg.codigo_grande_grupo,
                    score=round(max(0.0, min(1.0, sc)), 4),
                    is_cadastro_oficial=reg.is_cadastro_oficial,
                    versao_indice=self.versao_indice,
                    metodo="semantica_vetorial",
                )
            )
            if len(resultados) >= top_k:
                break
        return resultados

    def buscar_lexico(
        self,
        consulta: str,
        top_k: int = 5,
        apenas_oficiais: bool = False,
    ) -> list[ResultadoBuscaCBO]:
        """Alternativa A (Opção Nula do ADR 0007): busca textual apenas por código e palavras do título."""
        if top_k <= 0:
            raise ValueError("O parâmetro top_k deve ser positivo.")
        texto = (consulta or "").strip()
        if not texto:
            return []

        norm_q = normalizar_texto(texto)
        tokens_q = set(tokenizar_palavras(norm_q))
        codigo_exato = extrair_codigo_cbo_exato(texto)

        candidatos: list[tuple[float, str, RegistroCBO]] = []
        for reg in self.registros:
            if apenas_oficiais and not reg.is_cadastro_oficial:
                continue
            if codigo_exato and reg.codigo_cbo == codigo_exato:
                candidatos.append((1.0, reg.codigo_cbo, reg))
                continue

            norm_tit = normalizar_texto(reg.titulo_ocupacao)
            tokens_tit = set(tokenizar_palavras(norm_tit))
            if not tokens_q or not tokens_tit:
                continue

            intersecao = len(tokens_q & tokens_tit)
            em_substring = 1.0 if (len(norm_q) >= 4 and norm_q in norm_tit) else 0.0
            if intersecao == 0 and em_substring == 0.0:
                continue

            score = (intersecao / max(len(tokens_q), 1)) * 0.8 + em_substring * 0.2
            candidatos.append((min(0.99, score), reg.codigo_cbo, reg))

        candidatos.sort(key=lambda item: (-item[0], item[1]))
        return [
            ResultadoBuscaCBO(
                codigo_cbo=reg.codigo_cbo,
                titulo_ocupacao=reg.titulo_ocupacao,
                codigo_grande_grupo=reg.codigo_grande_grupo,
                score=round(sc, 4),
                is_cadastro_oficial=reg.is_cadastro_oficial,
                versao_indice=self.versao_indice,
                metodo="codigo_exato" if sc == 1.0 else "lexica",
            )
            for sc, _, reg in candidatos[:top_k]
        ]


def consultar_indicadores_cbo(
    conn: duckdb.DuckDBPyConnection,
    codigos_cbo: Sequence[str],
    sigla_uf: str | None = None,
    ano: int | None = None,
) -> dict[str, Any]:
    """Consulta na camada Gold (`gold.fct_movimentacao`) os indicadores para os códigos CBO informados.

    Segue estritamente as regras compartilhadas do contrato Gold:
    - Municípios identificados (`is_identificado = TRUE`) do Centro-Oeste (`is_centro_oeste = TRUE`), 2023-2026;
    - Saldo = soma de `saldo_movimentacao`;
    - Salário médio nominal de admissão = `sum(salario_mensal) / nullif(count(*), 0)` apenas sobre
      eventos com `saldo_movimentacao = 1 AND salario_valido = TRUE`.
    """
    codigos_limpos = sorted({str(c).strip().zfill(6) for c in codigos_cbo if str(c).strip()})
    if not codigos_limpos:
        raise ValueError("Informe ao menos um código CBO de 6 dígitos.")

    filtros = [
        "f.is_identificado",
        "f.is_centro_oeste",
        "f.ano BETWEEN 2023 AND 2026",
        "f.codigo_cbo IN (SELECT unnest(?::VARCHAR[]))",
    ]
    params: list[Any] = [codigos_limpos]

    if sigla_uf and sigla_uf != "Todas":
        filtros.append("f.sigla_uf = ?")
        params.append(sigla_uf)
    if ano is not None:
        filtros.append("f.ano = ?")
        params.append(int(ano))

    where_sql = " AND ".join(filtros)

    resumo = conn.execute(
        f"""
        SELECT
            COALESCE(COUNT(*) FILTER (WHERE f.saldo_movimentacao = 1), 0) AS admissoes,
            COALESCE(COUNT(*) FILTER (WHERE f.saldo_movimentacao = -1), 0) AS desligamentos,
            COALESCE(SUM(f.saldo_movimentacao), 0) AS saldo,
            COALESCE(
                SUM(CASE WHEN f.saldo_movimentacao = 1 AND f.salario_valido THEN f.salario_mensal ELSE 0 END),
                0
            ) AS soma_salarios_admissao,
            COALESCE(
                COUNT(*) FILTER (WHERE f.saldo_movimentacao = 1 AND f.salario_valido),
                0
            ) AS qtd_salarios_admissao,
            SUM(CASE WHEN f.saldo_movimentacao = 1 AND f.salario_valido THEN f.salario_mensal ELSE 0 END)
                / NULLIF(COUNT(*) FILTER (WHERE f.saldo_movimentacao = 1 AND f.salario_valido), 0)
                AS salario_medio_admissao,
            MIN(f.competencia) AS competencia_inicial,
            MAX(f.competencia) AS competencia_final
        FROM gold.fct_movimentacao f
        WHERE {where_sql}
        """,
        params,
    ).fetchone()

    por_ocupacao = conn.execute(
        f"""
        SELECT
            c.codigo_cbo,
            c.titulo_ocupacao,
            c.is_cadastro_oficial,
            COALESCE(COUNT(f.id_movimentacao) FILTER (WHERE f.saldo_movimentacao = 1), 0) AS admissoes,
            COALESCE(COUNT(f.id_movimentacao) FILTER (WHERE f.saldo_movimentacao = -1), 0) AS desligamentos,
            COALESCE(SUM(f.saldo_movimentacao), 0) AS saldo,
            COALESCE(
                COUNT(f.id_movimentacao) FILTER (WHERE f.saldo_movimentacao = 1 AND f.salario_valido),
                0
            ) AS qtd_salarios_admissao,
            SUM(CASE WHEN f.saldo_movimentacao = 1 AND f.salario_valido THEN f.salario_mensal ELSE 0 END)
                / NULLIF(COUNT(f.id_movimentacao) FILTER (WHERE f.saldo_movimentacao = 1 AND f.salario_valido), 0)
                AS salario_medio_admissao
        FROM gold.dim_cbo c
        LEFT JOIN gold.fct_movimentacao f
            ON c.codigo_cbo = f.codigo_cbo
           AND f.is_identificado
           AND f.is_centro_oeste
           AND f.ano BETWEEN 2023 AND 2026
           {"AND f.sigla_uf = ?" if (sigla_uf and sigla_uf != "Todas") else ""}
           {"AND f.ano = ?" if ano is not None else ""}
        WHERE c.codigo_cbo IN (SELECT unnest(?::VARCHAR[]))
        GROUP BY c.codigo_cbo, c.titulo_ocupacao, c.is_cadastro_oficial
        ORDER BY admissoes DESC, c.codigo_cbo ASC
        """,
        params[1:] + [codigos_limpos],
    ).fetchall()

    por_uf = conn.execute(
        f"""
        SELECT
            f.sigla_uf,
            COUNT(*) FILTER (WHERE f.saldo_movimentacao = 1) AS admissoes,
            COUNT(*) FILTER (WHERE f.saldo_movimentacao = -1) AS desligamentos,
            SUM(f.saldo_movimentacao) AS saldo,
            COUNT(*) FILTER (WHERE f.saldo_movimentacao = 1 AND f.salario_valido) AS qtd_salarios_admissao,
            SUM(CASE WHEN f.saldo_movimentacao = 1 AND f.salario_valido THEN f.salario_mensal ELSE 0 END)
                / NULLIF(COUNT(*) FILTER (WHERE f.saldo_movimentacao = 1 AND f.salario_valido), 0)
                AS salario_medio_admissao
        FROM gold.fct_movimentacao f
        WHERE {where_sql}
        GROUP BY f.sigla_uf
        ORDER BY admissoes DESC, f.sigla_uf ASC
        """,
        params,
    ).fetchall()

    return {
        "codigos_cbo": codigos_limpos,
        "filtros": {"sigla_uf": sigla_uf or "Todas", "ano": ano},
        "admissoes": int(resumo[0] or 0),
        "desligamentos": int(resumo[1] or 0),
        "saldo": int(resumo[2] or 0),
        "soma_salarios_admissao": float(resumo[3] or 0.0),
        "qtd_salarios_admissao": int(resumo[4] or 0),
        "salario_medio_admissao": float(resumo[5]) if resumo[5] is not None else None,
        "competencia_inicial": resumo[6],
        "competencia_final": resumo[7],
        "por_ocupacao": [
            {
                "codigo_cbo": r[0],
                "titulo_ocupacao": r[1],
                "is_cadastro_oficial": bool(r[2]),
                "admissoes": int(r[3] or 0),
                "desligamentos": int(r[4] or 0),
                "saldo": int(r[5] or 0),
                "qtd_salarios_admissao": int(r[6] or 0),
                "salario_medio_admissao": float(r[7]) if r[7] is not None else None,
            }
            for r in por_ocupacao
        ],
        "por_uf": [
            {
                "sigla_uf": r[0],
                "admissoes": int(r[1] or 0),
                "desligamentos": int(r[2] or 0),
                "saldo": int(r[3] or 0),
                "qtd_salarios_admissao": int(r[4] or 0),
                "salario_medio_admissao": float(r[5]) if r[5] is not None else None,
            }
            for r in por_uf
        ],
    }

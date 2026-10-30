select
    competencia, sigla_uf, is_capital, codigo_secao, id_perfil_demografico,
    {{ metricas_movimentacao() }}
from {{ ref('fct_movimentacao') }}
where is_identificado and is_centro_oeste and ano between 2023 and 2026
group by competencia, sigla_uf, is_capital, codigo_secao, id_perfil_demografico

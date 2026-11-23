-- Proxy de equilíbrio dos fluxos, sem estoque de empregados: não é taxa convencional de turnover.
with base as (
    select * from {{ ref('fct_setor_mensal') }}
    where codigo_secao <> 'Z'
    -- Aplique aqui os filtros de período/UF, antes de recalcular o índice.
), setores as (
    -- Métricas recompostas das medidas aditivas pela camada semântica (metricas.yml).
    select codigo_secao,
           {%- for m in ['admissoes', 'desligamentos', 'saldo', 'soma_salarios_admissao',
                         'qtd_salarios_admissao', 'salario_medio_admissao',
                         'indice_fluxos_pareados_pct'] %}
           {{ metrica(m, 'agregado') }} as {{ m }}{{ ',' if not loop.last }}
           {%- endfor %}
    from base group by codigo_secao
), pares as (
    select * from setores
    where indice_fluxos_pareados_pct is not null and salario_medio_admissao is not null
), correlacao as (
    select count(*) as pares_validos,
           case when count(*) >= 3
                  and stddev_pop(indice_fluxos_pareados_pct) > 0
                  and stddev_pop(salario_medio_admissao) > 0
                then corr(indice_fluxos_pareados_pct, salario_medio_admissao)
           end as correlacao_pearson
    from pares
)
select s.*, c.pares_validos, c.correlacao_pearson
from setores s cross join correlacao c
order by codigo_secao

-- Proxy de equilíbrio dos fluxos, sem estoque de empregados: não é taxa convencional de turnover.
with base as (
    select * from {{ ref('fct_setor_mensal') }}
    where codigo_secao <> 'Z'
    -- Aplique aqui os filtros de período/UF, antes de recalcular o índice.
), totais as (
    select codigo_secao,
           sum(admissoes) as admissoes, sum(desligamentos) as desligamentos,
           sum(saldo) as saldo,
           sum(soma_salarios_admissao) as soma_salarios_admissao,
           sum(qtd_salarios_admissao) as qtd_salarios_admissao
    from base group by codigo_secao
), setores as (
    select *, soma_salarios_admissao / nullif(qtd_salarios_admissao, 0) as salario_medio_admissao,
           200.0 * least(admissoes, desligamentos)
               / nullif(admissoes + desligamentos, 0) as indice_fluxos_pareados_pct
    from totais
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

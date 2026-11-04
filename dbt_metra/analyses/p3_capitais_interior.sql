-- Filtros de período/UF devem ser aplicados em base, antes dos GROUPING SETS.
with base as (
    select *, year(competencia)::integer as ano
    from {{ ref('fct_geografia_mensal') }}
), grupos as (
    select competencia, ano,
           case when grouping(sigla_uf) = 1 then 'Centro-Oeste' else sigla_uf end as recorte,
           case when grouping(competencia) = 0 then 'mensal'
                when grouping(ano) = 0 then 'anual' else 'total' end as nivel,
           is_capital,
           sum(admissoes) as admissoes, sum(desligamentos) as desligamentos,
           sum(saldo) as saldo,
           sum(soma_salarios_admissao) / nullif(sum(qtd_salarios_admissao), 0) as salario,
           sum(qtd_salarios_admissao) as n_salarios
    from base
    group by grouping sets (
        (competencia, sigla_uf, is_capital), (competencia, is_capital),
        (ano, sigla_uf, is_capital), (ano, is_capital),
        (sigla_uf, is_capital), (is_capital)
    )
), comparacao as (
    select nivel, competencia, ano, recorte,
           max(admissoes) filter (where is_capital) as admissoes_capital,
           max(admissoes) filter (where not is_capital) as admissoes_interior,
           max(desligamentos) filter (where is_capital) as desligamentos_capital,
           max(desligamentos) filter (where not is_capital) as desligamentos_interior,
           max(saldo) filter (where is_capital) as saldo_capital,
           max(saldo) filter (where not is_capital) as saldo_interior,
           max(salario) filter (where is_capital) as salario_capital,
           max(salario) filter (where not is_capital) as salario_interior,
           coalesce(max(n_salarios) filter (where is_capital), 0) as n_capital,
           coalesce(max(n_salarios) filter (where not is_capital), 0) as n_interior
    from grupos group by nivel, competencia, ano, recorte
)
select *,
       saldo_capital - saldo_interior as diferenca_saldo,
       salario_capital - salario_interior as diferenca_salario
from comparacao
order by nivel, competencia nulls last, ano nulls last, recorte

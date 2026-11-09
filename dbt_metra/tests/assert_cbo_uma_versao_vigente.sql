-- SCD tipo 2: no máximo uma versão vigente por ocupação (nenhuma, se ela saiu da fonte)
-- e períodos encadeados, sem sobreposição.

with versoes as (
    select
        codigo_cbo,
        observado_desde,
        observado_ate,
        is_versao_vigente,
        lead(observado_desde) over (partition by codigo_cbo order by observado_desde) as proxima_observacao_desde
    from {{ ref('dim_cbo_historico') }}
)

select codigo_cbo, 'mais de uma versao vigente' as violacao
from versoes
group by codigo_cbo
having count(*) filter (where is_versao_vigente) > 1

union all

-- A versão encerrada termina exatamente quando a seguinte começa.
select codigo_cbo, 'periodo nao encadeado' as violacao
from versoes
where proxima_observacao_desde is not null
  and observado_ate is distinct from proxima_observacao_desde

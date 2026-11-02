with presentes as (
    select distinct competencia from {{ ref('stg_movimentacao') }}
), calendario as (
    select unnest(generate_series(min(competencia), max(competencia), interval '1 month'))::date as competencia
    from presentes
)
select
    c.competencia,
    year(c.competencia)::integer as ano,
    month(c.competencia)::integer as mes,
    quarter(c.competencia)::integer as trimestre,
    p.competencia is not null as tem_dados
from calendario c
left join presentes p using (competencia)

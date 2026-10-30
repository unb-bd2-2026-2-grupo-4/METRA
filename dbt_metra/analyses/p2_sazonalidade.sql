-- Aplique filtros de período/UF em base; filtre setores depois da construção da série.
with base as (
    select * from {{ ref('fct_setor_mensal') }}
), competencias as (
    select distinct competencia from base
), calendario as (
    select c.competencia, c.ano, c.mes, p.competencia is not null as tem_dados
    from {{ ref('dim_competencia') }} c
    left join competencias p using (competencia)
    where c.competencia between (select min(competencia) from base)
                            and (select max(competencia) from base)
), anos_completos as (
    select ano from calendario
    group by ano having count(*) filter (where tem_dados) = 12
), grupos as (
    select distinct sigla_uf, codigo_secao from base
), serie as (
    select c.*, g.sigla_uf, g.codigo_secao,
           a.ano is not null as ano_completo_na_base,
           case when c.tem_dados then coalesce(b.admissoes, 0) end as admissoes,
           case when c.tem_dados then coalesce(b.desligamentos, 0) end as desligamentos,
           case when c.tem_dados then coalesce(b.saldo, 0) end as saldo
    from calendario c cross join grupos g
    left join base b using (competencia, sigla_uf, codigo_secao)
    left join anos_completos a on c.ano = a.ano
), resumo as (
    select sigla_uf, codigo_secao, mes,
           count(*) as anos_considerados,
           avg(admissoes) as media_admissoes_mes,
           avg(desligamentos) as media_desligamentos_mes,
           avg(saldo) as media_saldo_mes
    from serie where ano_completo_na_base
    group by sigla_uf, codigo_secao, mes
)
select s.*, coalesce(r.anos_considerados, 0) as anos_considerados,
       r.media_admissoes_mes, r.media_desligamentos_mes, r.media_saldo_mes
from serie s
left join resumo r using (sigla_uf, codigo_secao, mes)
order by sigla_uf, codigo_secao, competencia

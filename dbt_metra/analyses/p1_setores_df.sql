-- P1: janela de calendário ancorada nos dados, sem depender de current_date.
with base as (
    select * from {{ ref('fct_setor_mensal') }}
), janela as (
    select (max(competencia) - interval '11 months')::date as inicio,
           max(competencia) as fim
    from base
), cobertura as (
    select count(distinct competencia) as competencias_disponiveis
    from base cross join janela
    where competencia between inicio and fim
), setores as (
    select codigo_secao,
           sum(admissoes) as admissoes, sum(desligamentos) as desligamentos,
           sum(saldo) as saldo
    from base cross join janela
    where sigla_uf = 'DF' and codigo_secao <> 'Z'
      and competencia between inicio and fim
    group by codigo_secao
), secoes as (
    select distinct codigo_secao, descricao_secao from {{ ref('dim_cnae') }}
)
select s.*, d.descricao_secao,
       dense_rank() over (order by admissoes desc) as ranking_admissoes,
       dense_rank() over (order by desligamentos desc) as ranking_desligamentos,
       j.inicio, j.fim, c.competencias_disponiveis
from setores s
left join secoes d using (codigo_secao)
cross join janela j
cross join cobertura c
order by ranking_admissoes, codigo_secao

-- Comparação descritiva de eventos; não estima probabilidade de recolocação nem efeito causal.
with base as (
    select f.*, p.* exclude (id_perfil_demografico)
    from {{ ref('fct_perfil_mensal') }} f
    left join {{ ref('dim_perfil_demografico') }} p using (id_perfil_demografico)
    -- Aplique aqui os filtros de período/UF/localidade/setor.
), eixos as (
    select b.sigla_uf, b.is_capital, b.codigo_secao,
           e.eixo, e.codigo_categoria, e.categoria,
           b.admissoes, b.desligamentos, b.saldo,
           b.soma_salarios_admissao, b.qtd_salarios_admissao
    from base b
    cross join lateral (values
        ('sexo', b.codigo_sexo, b.sexo),
        ('raca_cor', b.codigo_raca_cor, b.raca_cor),
        ('escolaridade', b.codigo_grau_instrucao, b.escolaridade),
        ('faixa_etaria', b.codigo_faixa_etaria, b.faixa_etaria)
    ) e(eixo, codigo_categoria, categoria)
), grupos as (
    select sigla_uf, is_capital, codigo_secao, eixo, codigo_categoria, categoria,
           sum(admissoes) as admissoes, sum(desligamentos) as desligamentos,
           sum(saldo) as saldo,
           sum(soma_salarios_admissao) as soma_salarios_admissao,
           sum(qtd_salarios_admissao) as qtd_salarios_admissao
    from eixos group by sigla_uf, is_capital, codigo_secao, eixo, codigo_categoria, categoria
), referencias as (
    select *, soma_salarios_admissao / nullif(qtd_salarios_admissao, 0) as salario_medio_admissao,
           sum(admissoes) over recorte as admissoes_recorte,
           sum(soma_salarios_admissao) over recorte
               / nullif(sum(qtd_salarios_admissao) over recorte, 0) as salario_medio_recorte
    from grupos
    window recorte as (partition by sigla_uf, is_capital, codigo_secao, eixo)
)
select *,
       100.0 * admissoes / nullif(admissoes_recorte, 0) as participacao_admissoes_pct,
       salario_medio_admissao - salario_medio_recorte as diferenca_salarial,
       100.0 * (salario_medio_admissao - salario_medio_recorte)
           / nullif(salario_medio_recorte, 0) as diferenca_salarial_pct
from referencias
order by sigla_uf, is_capital, codigo_secao, eixo, codigo_categoria

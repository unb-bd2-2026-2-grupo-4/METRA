-- Fluxos por competência, UF, capital/interior, seção CNAE e categoria de um eixo
-- demográfico por vez (P5), sem grupos pequenos. Os eixos não se cruzam: cruzar
-- sexo, raça/cor, escolaridade e idade criaria grupos menores e reidentificáveis.
with eixos as (
    select f.competencia, f.sigla_uf, f.is_capital, f.codigo_secao,
           e.eixo, e.codigo_categoria, e.categoria,
           f.admissoes, f.desligamentos, f.saldo,
           f.soma_salarios_admissao, f.qtd_salarios_admissao
    from {{ ref('fct_perfil_mensal') }} f
    join {{ ref('dim_perfil_demografico') }} p using (id_perfil_demografico)
    cross join lateral (values
        ('sexo', p.codigo_sexo, p.sexo),
        ('raca_cor', p.codigo_raca_cor, p.raca_cor),
        ('escolaridade', p.codigo_grau_instrucao, p.escolaridade),
        ('faixa_etaria', p.codigo_faixa_etaria, p.faixa_etaria)
    ) e(eixo, codigo_categoria, categoria)
), publicado as (
    {{ publicar_grupos('eixos', [
        'competencia', 'sigla_uf', 'is_capital', 'codigo_secao', 'eixo', 'codigo_categoria', 'categoria',
    ]) }}
)
select * from publicado

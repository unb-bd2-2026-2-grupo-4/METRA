-- LEFT JOIN mantém os eventos; referências ausentes devem ser detectadas pelos testes de integridade.
with eventos as (
    select *, {{ faixa_etaria('idade') }} as codigo_faixa_etaria
    from {{ ref('stg_movimentacao') }}
)
select
    m.*,
    p.id_perfil_demografico,
    mun.sigla_uf,
    mun.is_capital,
    mun.is_identificado,
    mun.is_centro_oeste,
    cnae.codigo_secao,
    cbo.codigo_grande_grupo,
    c.tem_dados as competencia_tem_dados
from eventos m
left join {{ ref('dim_competencia') }} c using (competencia)
left join {{ ref('dim_municipio') }} mun using (id_municipio)
left join {{ ref('dim_cnae') }} cnae using (codigo_cnae_subclasse)
left join {{ ref('dim_cbo') }} cbo using (codigo_cbo)
left join {{ ref('dim_perfil_demografico') }} p
    using (codigo_sexo, codigo_raca_cor, codigo_grau_instrucao, codigo_faixa_etaria)

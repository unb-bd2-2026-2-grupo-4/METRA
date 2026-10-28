-- Subclasses da CNAE 2.0 com a seção correspondente.
-- A junção reúne a mesma classificação, separada em duas tabelas pela 3FN da origem.

with subclasse as (

    select * from {{ source('lake', 'cnae_subclasse') }}

),

secao as (

    select * from {{ source('lake', 'cnae_secao') }}

)

select
    subclasse.codigo as codigo_cnae_subclasse,
    subclasse.descricao as descricao_subclasse,
    subclasse.codigo_secao,
    secao.descricao as descricao_secao,
    -- A E1 cria o sentinela 9999999 (seção Z) e subclasses administrativas
    -- para códigos do CAGED ausentes da API do IBGE.
    subclasse.codigo <> '9999999'
        and subclasse.descricao not like '% (REGISTRO ADMINISTRATIVO)' as is_cadastro_oficial

from subclasse
inner join secao
    on subclasse.codigo_secao = secao.codigo

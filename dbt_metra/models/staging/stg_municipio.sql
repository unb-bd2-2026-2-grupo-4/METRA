-- Municípios do IBGE, com marcação do sentinela e do recorte regional do projeto.

select
    id_municipio,
    nome as nome_municipio,
    sigla_uf,
    nome_uf,
    regiao,
    is_capital,
    -- 9999999 é o registro criado pela E1 para movimentações sem município.
    id_municipio <> '9999999' as is_identificado,
    sigla_uf in ('DF', 'GO', 'MT', 'MS') as is_centro_oeste

from {{ source('lake', 'municipio') }}

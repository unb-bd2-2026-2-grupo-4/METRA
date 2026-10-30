-- Ocupações da CBO 2002, com o grande grupo ocupacional derivado do código.

select
    codigo as codigo_cbo,
    titulo as titulo_ocupacao,
    left(codigo, 1) as codigo_grande_grupo,
    -- A E1 cria títulos genéricos para códigos do CAGED ausentes da base oficial.
    titulo not like '% (ATUALIZACAO MTE)' as is_cadastro_oficial

from {{ source('lake', 'cbo_2002') }}

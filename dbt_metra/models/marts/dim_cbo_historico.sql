-- Dimensão de variação lenta (SCD tipo 2) da CBO: uma linha por versão de cada ocupação.
-- dim_cbo continua com a versão vigente (tipo 1), usada pelos fatos e pelo painel.

select
    dbt_scd_id as id_versao_cbo,
    codigo_cbo,
    titulo_ocupacao,
    codigo_grande_grupo,
    is_cadastro_oficial,
    dbt_valid_from as observado_desde,
    dbt_valid_to as observado_ate,
    dbt_valid_to is null as is_versao_vigente

from {{ ref('snp_cbo') }}

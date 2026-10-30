-- Movimentações do Novo CAGED padronizadas, uma linha por movimentação da origem.
-- Os códigos demográficos permanecem como na origem; os rótulos ficam nas dimensões da Gold.

with origem as (

    select * from {{ source('lake', 'movimentacao') }}

),

-- id_movimentacao é a chave da origem: protege a Silver contra arquivos repetidos no lake.
deduplicada as (

    select *
    from origem
    qualify row_number() over (partition by id_movimentacao order by registrado_em desc) = 1

)

select
    id_movimentacao,
    ano,
    mes,
    make_date(ano, mes, 1) as competencia,

    id_municipio,
    cnae_2_subclasse as codigo_cnae_subclasse,
    cbo_2002 as codigo_cbo,

    sexo as codigo_sexo,
    raca_cor as codigo_raca_cor,
    idade,
    grau_instrucao as codigo_grau_instrucao,

    tipo_movimentacao as codigo_tipo_movimentacao,
    saldo_movimentacao,
    case saldo_movimentacao
        when 1 then 'admissao'
        when -1 then 'desligamento'
    end as tipo_evento,

    -- A E1 grava salário ausente ou negativo como zero; só salário positivo entra em médias.
    salario_mensal,
    salario_mensal > 0 as salario_valido,
    horas_contratuais,

    id_ingestao,
    numero_linha,
    registrado_em

from deduplicada

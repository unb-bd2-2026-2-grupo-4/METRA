with perfis as (
    select distinct
        codigo_sexo, codigo_raca_cor, codigo_grau_instrucao,
        {{ faixa_etaria('idade') }} as codigo_faixa_etaria
    from {{ ref('stg_movimentacao') }}
)
select
    concat_ws('|', codigo_sexo, codigo_raca_cor, codigo_grau_instrucao, codigo_faixa_etaria) as id_perfil_demografico,
    codigo_sexo,
    case codigo_sexo
        when 1 then 'Homem' when 3 then 'Mulher' when 9 then 'Não identificado'
        else 'Código não mapeado'
    end as sexo,
    codigo_raca_cor,
    case codigo_raca_cor
        when 1 then 'Branca' when 2 then 'Preta' when 3 then 'Parda'
        when 4 then 'Amarela' when 5 then 'Indígena'
        when 6 then 'Não informada' when 9 then 'Não identificada'
        else 'Código não mapeado'
    end as raca_cor,
    codigo_grau_instrucao,
    case codigo_grau_instrucao
        when 1 then 'Analfabeto' when 2 then 'Até 5ª incompleto'
        when 3 then '5ª completo fundamental' when 4 then '6ª a 9ª fundamental'
        when 5 then 'Fundamental completo' when 6 then 'Médio incompleto'
        when 7 then 'Médio completo' when 8 then 'Superior incompleto'
        when 9 then 'Superior completo' when 10 then 'Mestrado'
        when 11 then 'Doutorado' when 80 then 'Pós-graduação completa'
        when 99 then 'Não identificado' else 'Código não mapeado'
    end as escolaridade,
    codigo_faixa_etaria,
    case codigo_faixa_etaria
        when 0 then 'Não informada' when 1 then 'Até 17'
        when 2 then '18–24' when 3 then '25–29' when 4 then '30–39'
        when 5 then '40–49' when 6 then '50–64' when 7 then '65 ou mais'
    end as faixa_etaria
from perfis

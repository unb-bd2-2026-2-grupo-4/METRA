{#-
    Controle de acesso por agregação: as views do schema consumo só publicam grupos
    com pelo menos `metra_limite_publicacao` movimentações (admissões + desligamentos)
    e só divulgam medidas salariais com pelo menos esse número de salários válidos.
    Abaixo do limite, o grupo é omitido; o salário fica nulo e os fluxos permanecem.
-#}

{% macro limite_publicacao() -%}
    {{- return(var('metra_limite_publicacao', 5)) -}}
{%- endmacro %}

{#- Agrupa `fonte` pelas `dimensoes`, recompõe as medidas pela camada semântica e
    aplica a supressão de pequenos grupos. -#}
{% macro publicar_grupos(fonte, dimensoes) -%}
    {%- set limite = limite_publicacao() -%}
    {%- set grupo = dimensoes | join(', ') -%}
    with grupos as (
        select {{ grupo }},
            {%- for m in ['admissoes', 'desligamentos', 'saldo', 'soma_salarios_admissao', 'qtd_salarios_admissao'] %}
            {{ metrica(m, 'agregado') }} as {{ m }}{{ ',' if not loop.last }}
            {%- endfor %}
        from {{ fonte }}
        group by {{ grupo }}
    )
    select {{ grupo }},
        admissoes,
        desligamentos,
        saldo,
        case when qtd_salarios_admissao >= {{ limite }} then soma_salarios_admissao end as soma_salarios_admissao,
        case when qtd_salarios_admissao >= {{ limite }} then qtd_salarios_admissao end as qtd_salarios_admissao
    from grupos
    where admissoes + desligamentos >= {{ limite }}
{%- endmacro %}

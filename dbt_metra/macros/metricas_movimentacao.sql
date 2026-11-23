{#- Medidas e métricas de movimentação dos marts, compiladas da camada semântica
    (models/semantic/metricas.yml). Os nomes das colunas são os nomes das métricas. -#}
{% macro metricas_movimentacao() -%}
    {%- for nome in ['admissoes', 'desligamentos', 'saldo', 'soma_salarios_admissao',
                     'qtd_salarios_admissao', 'salario_medio_admissao'] %}
    {{ metrica(nome, 'evento') }} as {{ nome }}{{ ',' if not loop.last }}
    {%- endfor %}
{%- endmacro %}

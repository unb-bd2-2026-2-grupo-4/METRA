{#
    Usa o schema configurado no modelo sem prefixar o schema do alvo,
    para que as camadas se chamem "silver" e "gold" em vez de "main_silver".
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}

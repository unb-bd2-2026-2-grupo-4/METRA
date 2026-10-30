{% macro faixa_etaria(idade) -%}
    case
        when {{ idade }} is null then 0
        when {{ idade }} <= 17 then 1
        when {{ idade }} <= 24 then 2
        when {{ idade }} <= 29 then 3
        when {{ idade }} <= 39 then 4
        when {{ idade }} <= 49 then 5
        when {{ idade }} <= 64 then 6
        else 7
    end
{%- endmacro %}

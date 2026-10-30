{% macro metricas_movimentacao() -%}
    count(*) filter (where saldo_movimentacao = 1) as admissoes,
    count(*) filter (where saldo_movimentacao = -1) as desligamentos,
    sum(saldo_movimentacao) as saldo,
    sum(case when saldo_movimentacao = 1 and salario_valido
        then salario_mensal else 0 end) as soma_salarios_admissao,
    count(*) filter (where saldo_movimentacao = 1 and salario_valido) as qtd_salarios_admissao,
    soma_salarios_admissao / nullif(qtd_salarios_admissao, 0) as salario_medio_admissao
{%- endmacro %}

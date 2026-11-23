-- As views de consumo publicam exatamente os grupos da Gold com pelo menos o limite de
-- movimentações, com os mesmos fluxos, e só divulgam salário a partir do limite.
-- Retorna as linhas que violam isso: grupo faltando, sobrando ou alterado.
{% set limite = var('metra_limite_publicacao') %}
{% set fontes = [
    ('setor_mensal', 'fct_setor_mensal', ['competencia', 'sigla_uf', 'codigo_secao']),
    ('geografia_mensal', 'fct_geografia_mensal', ['competencia', 'sigla_uf', 'is_capital']),
] %}
{% for view, fato, chave in fontes %}
select '{{ view }}' as view, coalesce(g.competencia, c.competencia) as competencia,
       g.admissoes as admissoes_gold, c.admissoes as admissoes_consumo
from (
    select {{ chave | join(', ') }}, admissoes, desligamentos, saldo,
           soma_salarios_admissao, qtd_salarios_admissao
    from {{ ref(fato) }}
    where admissoes + desligamentos >= {{ limite }}
) g
full outer join {{ ref(view) }} c using ({{ chave | join(', ') }})
where g.admissoes is null
   or c.admissoes is null
   or (g.admissoes, g.desligamentos, g.saldo) <> (c.admissoes, c.desligamentos, c.saldo)
   or c.qtd_salarios_admissao is distinct from
      (case when g.qtd_salarios_admissao >= {{ limite }} then g.qtd_salarios_admissao end)
   or c.soma_salarios_admissao is distinct from
      (case when g.qtd_salarios_admissao >= {{ limite }} then g.soma_salarios_admissao end)
{% if not loop.last %}union all{% endif %}
{% endfor %}

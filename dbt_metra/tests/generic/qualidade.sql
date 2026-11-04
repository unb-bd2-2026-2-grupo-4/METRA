-- Cada teste retorna somente as linhas que violam seu contrato.
{% test metra_expression(model, expression) %}
select * from {{ model }} where ({{ expression }}) is not true
{% endtest %}

{% test metra_column_types(model, expected) %}
-- Contrato do schema materializado, inclusive colunas removidas ou inesperadas.
with esperado(nome, tipo) as (
    values
    {% for nome, tipo in expected.items() %}
        ('{{ nome }}', '{{ tipo }}'){% if not loop.last %},{% endif %}
    {% endfor %}
), atual as (
    select column_name as nome, data_type as tipo
    from information_schema.columns
    where table_catalog = '{{ model.database | replace("'", "''") }}'
      and table_schema = '{{ model.schema | replace("'", "''") }}'
      and table_name = '{{ model.identifier | replace("'", "''") }}'
)
select coalesce(e.nome, a.nome) as coluna, e.tipo as esperado, a.tipo as encontrado
from esperado e full outer join atual a using (nome)
where e.tipo is distinct from a.tipo
{% endtest %}

{% test metra_not_empty(model) %}
select count(*) as total from {{ model }} having count(*) = 0
{% endtest %}

{% test metra_unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*) as total
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}

{% test metra_same_count(model, compare_model, distinct_key=none) %}
with atual as (
    select count(*) as total from {{ model }}
), origem as (
    select count({% if distinct_key %}distinct {{ distinct_key }}{% else %}*{% endif %}) as total
    from {{ compare_model }}
)
select atual.total as total_atual, origem.total as total_origem
from atual cross join origem where atual.total <> origem.total
{% endtest %}

{% test metra_same_distribution(model, compare_model, dimensions, compare_dimensions) %}
-- Igualdade da distribuição por grupos: uma contagem global sozinha não
-- detectaria troca de municípios, competências ou perfis demográficos.
with atual as (
    select
        {% for col in dimensions %}{{ col }} as d{{ loop.index }},{% endfor %}
        count(*) as total
    from {{ model }}
    group by {{ dimensions | join(', ') }}
), origem as (
    select
        {% for col in compare_dimensions %}{{ col }} as d{{ loop.index }},{% endfor %}
        count(distinct id_movimentacao) as total
    from {{ compare_model }}
    group by {{ compare_dimensions | join(', ') }}
)
select atual.total as total_atual, origem.total as total_origem
    {% for col in dimensions %}, coalesce(atual.d{{ loop.index }}, origem.d{{ loop.index }}) as d{{ loop.index }}{% endfor %}
from atual full outer join origem on
    {% for col in dimensions %}
    atual.d{{ loop.index }} is not distinct from origem.d{{ loop.index }}
    {% if not loop.last %}and{% endif %}
    {% endfor %}
where atual.total is distinct from origem.total
{% endtest %}

{% test metra_monthly_volume(model, min_ratio=0.25, max_ratio=4.0) %}
-- Detecta lacunas e saltos; limites operacionais iniciais, não uma lei do domínio.
-- Usa todas as competências do intervalo observado, inclusive meses sem linhas.
with limites as (
    select min(competencia) as inicio, max(competencia) as fim from {{ model }}
), calendario as (
    select unnest(generate_series(inicio, fim, interval '1 month'))::date as competencia
    from limites
), volumes as (
    select competencia, count(*) as total from {{ model }} group by competencia
), serie as (
    select c.competencia, coalesce(v.total, 0) as total
    from calendario c left join volumes v using (competencia)
), comparacao as (
    select *, lag(total) over (order by competencia) as anterior from serie
)
select *, total::double / nullif(anterior, 0) as razao
from comparacao
where total = 0
   or (anterior > 0 and
       (total::double / anterior < {{ min_ratio }} or total::double / anterior > {{ max_ratio }}))
{% endtest %}

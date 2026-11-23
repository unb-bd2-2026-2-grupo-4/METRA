{#-
    Camada semântica: compila o SQL de uma métrica a partir da definição única em
    models/semantic/metricas.yml (lida do grafo do dbt). Não há fórmula aqui.

    origem='evento'   -> sobre gold.fct_movimentacao: aplica o agg de cada medida à expr.
    origem='agregado' -> sobre marts/CTEs que já têm as medidas como colunas: sum(<medida>).
    janela='nome'     -> (só com 'agregado') recompõe sobre uma janela nomeada: sum(<medida>) over nome.

    A mesma regra está em src/metricas/camada_semantica.py; tests/test_camada_semantica.py
    confere que os dois compiladores geram SQL idêntico.
-#}

{% macro _metra_medidas() -%}
    {%- set medidas = {} -%}
    {%- for sm in graph.semantic_models.values() -%}
        {%- for m in sm.measures -%}
            {%- do medidas.update({m.name: m}) -%}
        {%- endfor -%}
    {%- endfor -%}
    {{- return(medidas) -}}
{%- endmacro %}

{% macro _metra_metricas() -%}
    {%- set metricas = {} -%}
    {%- for mt in graph.metrics.values() -%}
        {%- do metricas.update({mt.name: mt}) -%}
    {%- endfor -%}
    {{- return(metricas) -}}
{%- endmacro %}

{% macro _metra_nome_ref(ref) -%}
    {#- No manifest, referências a medida/métrica são objetos com `name`. -#}
    {{- return(ref.name if ref is mapping else ref) -}}
{%- endmacro %}

{% macro _metra_sql_medida(nome, origem, janela=none) -%}
    {%- set medida = _metra_medidas()[nome] -%}
    {%- if origem == 'agregado' -%}
        {{- return('sum(' ~ nome ~ ')' ~ ((' over ' ~ janela) if janela else '')) -}}
    {%- else -%}
        {{- return(medida.agg ~ '(' ~ (medida.expr or nome) ~ ')') -}}
    {%- endif -%}
{%- endmacro %}

{% macro metrica(nome, origem='evento', janela=none) -%}
    {%- if not execute -%}
        {{- return('null') -}}
    {%- endif -%}
    {%- if origem not in ['evento', 'agregado'] -%}
        {{- exceptions.raise_compiler_error("origem inválida para metrica(): " ~ origem) -}}
    {%- endif -%}
    {%- if janela and origem != 'agregado' -%}
        {{- exceptions.raise_compiler_error("janela só é permitida com origem='agregado'") -}}
    {%- endif -%}
    {%- set metricas = _metra_metricas() -%}
    {%- if nome not in metricas -%}
        {{- exceptions.raise_compiler_error("métrica não definida em metricas.yml: " ~ nome) -}}
    {%- endif -%}
    {%- set mt = metricas[nome] -%}
    {%- set tp = mt.type_params -%}
    {%- if mt.type == 'simple' -%}
        {{- return(_metra_sql_medida(_metra_nome_ref(tp.measure), origem, janela)) -}}
    {%- elif mt.type == 'ratio' -%}
        {%- set num = metrica(_metra_nome_ref(tp.numerator), origem, janela) -%}
        {%- set den = metrica(_metra_nome_ref(tp.denominator), origem, janela) -%}
        {{- return(num ~ ' / nullif(' ~ den ~ ', 0)') -}}
    {%- elif mt.type == 'derived' -%}
        {#- Duas passadas com marcadores: o SQL de uma filha nunca é substituído de novo. -#}
        {%- set ns = namespace(sql=tp.expr) -%}
        {%- for filha in tp.metrics -%}
            {%- set ns.sql = modules.re.sub('\\b' ~ _metra_nome_ref(filha) ~ '\\b', '@@' ~ loop.index0 ~ '@@', ns.sql) -%}
        {%- endfor -%}
        {%- for filha in tp.metrics -%}
            {%- set ns.sql = ns.sql.replace('@@' ~ loop.index0 ~ '@@', '(' ~ metrica(_metra_nome_ref(filha), origem, janela) ~ ')') -%}
        {%- endfor -%}
        {{- return(ns.sql) -}}
    {%- else -%}
        {{- exceptions.raise_compiler_error("tipo de métrica não suportado: " ~ mt.type) -}}
    {%- endif -%}
{%- endmacro %}

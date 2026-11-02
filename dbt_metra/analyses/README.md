# Contratos SQL das perguntas de gestão

As consultas usam `ref()` e são compiladas por `dbt compile` em
`target/compiled/metra/analyses/`. Elas consultam tabelas do schema `gold`;
não são modelos materializados. A descrição de cada modelo, grão, chave e coluna
está em `models/marts/_gold__models.yml`.

## Regras compartilhadas

- Fatos agregadas: municípios identificados de DF, GO, MT e MS, de 2023 a 2026.
  A fato detalhada mantém todos os registros da Silver, incluindo sentinelas.
- Setor econômico significa **seção CNAE**, não subclasse. A dimensão tem uma
  linha por subclasse: não ligar agregados de seção diretamente a todas as suas
  linhas, pois isso multiplicaria contagens. P1 usa uma projeção distinta de seções.
- Admissões e desligamentos são contagens de **eventos**, não pessoas distintas.
  O sinal de `saldo_movimentacao`, e não o código do tipo de movimentação, define
  as duas contagens. Saldo = admissões − desligamentos.
- Salários são mensais, nominais em R$, sem deflação, poda de extremos ou ajuste
  por horas. Só admissões com salário positivo entram na soma e no denominador.
  Ausência de salário elegível produz média `NULL`.
- Reagrupar sempre por `sum(soma_salarios_admissao) /
  nullif(sum(qtd_salarios_admissao), 0)`. Não somar médias nem fazer média de médias.
  Arredondamento é responsabilidade da apresentação.
- Filtros devem ser aplicados no CTE `base` antes da recomposição das métricas.
  Valores ausentes não são automaticamente zeros; a regra específica de P2 está abaixo.
- Cobertura indica presença de registros na base. Não certifica que um mês foi
  integralmente publicado nem que a amostra representa o mercado inteiro. Não
  inferir saldo oficial ajustado, efeitos causais ou probabilidade de recolocação.

## P1 — Setores no DF (`p1_setores_df.sql`)

Uma linha por seção, com admissões, desligamentos, saldo, descrição e dois
rankings `dense_rank` independentes. Empates conservam a mesma posição; a seção
`Z` fica fora dos rankings. A janela inclui os 12 meses de calendário terminando
na última competência carregada do recorte agregado do Centro-Oeste. Não usa
os 12 últimos meses com registros nem o relógio da máquina.

`inicio`, `fim` e `competencias_disponiveis` descrevem a janela comum do recorte,
incluindo competências em que não houve eventos observados no DF. Na amostra
atual, a janela é fevereiro/2025 a janeiro/2026.

## P2 — Sazonalidade (`p2_sazonalidade.sql`)

Uma linha por competência × par UF/seção observado em algum momento do recorte.
O calendário inclui meses intermediários ausentes. `tem_dados = false` deixa
as contagens nulas; em mês presente no recorte, a ausência do par UF/seção é zero
observado. Um mês com apenas movimentações sentinela não conta como presente
no recorte dos agregados.

`ano_completo_na_base` exige 12 competências presentes no recorte. O resumo por
mês do ano inclui somente esses anos: `media_admissoes_mes`,
`media_desligamentos_mes`, `media_saldo_mes` e `anos_considerados`. Na amostra,
2023–2025 entram e 2026 fica fora do resumo. Os campos do resumo são repetidos
nas linhas anuais correspondentes; selecione valores distintos por UF/seção/mês,
sem somá-los. Sem ano completo, as médias são nulas e `anos_considerados = 0`.

Filtros temporais ou de UF devem entrar em `base`. Filtros de seção entram
após a construção da série, preservando a distinção entre mês ausente e zero.
O resumo descreve padrões; não executa teste estatístico de sazonalidade.

## P3 — Capitais e interior (`p3_capitais_interior.sql`)

`nivel` distingue linhas `mensal`, `anual` e `total`; `recorte` distingue cada
UF de `Centro-Oeste`. `competencia` identifica linhas mensais e `ano` identifica
linhas anuais. O consolidado regional soma os numeradores e denominadores das
UFs antes de calcular salários, inclusive nas linhas anuais e totais.

Publica admissões, desligamentos, saldos, salários e denominadores de cada grupo;
as diferenças são sempre **capital − interior**. Grupo ausente deixa contagens,
saldo, média e diferenças nulos; seu denominador salarial fica em zero para
compatibilidade com `src/analise.py`. Isso se aplica ao interior do DF.
Não somar níveis temporais ou recortes sobrepostos.

## P4 — Fluxos pareados e salários (`p4_fluxos_salarios.sql`)

Uma linha por seção, consolidada sobre o período/UFs selecionados antes do
cálculo. A seção `Z` não entra. Cada linha publica volumes, componentes
salariais, média e a proxy:

```sql
200.0 * least(admissoes, desligamentos)
    / nullif(admissoes + desligamentos, 0)
```

`indice_fluxos_pareados_pct` varia entre 0 e 100: zero em fluxo unilateral,
100 com admissões e desligamentos iguais, e `NULL` com denominador zero.
É um índice de equilíbrio de entradas e saídas; não mede intensidade de
rotatividade sobre o estoque de empregados. Não somar nem tirar média simples
dos índices de competências diferentes.

`correlacao_pearson` é calculada entre proxy e salário médio, dando peso igual
a cada seção com ambos os indicadores não nulos. `pares_validos` informa o
número desses setores. Com menos de três pares, índice constante ou salário
constante, a correlação é `NULL`. Esses dois campos são repetidos nas linhas
setoriais e não devem ser somados.

## P5 — Perfil e remuneração (`p5_perfil_remuneracao.sql`)

Uma linha por UF × capital/interior × seção × eixo × código da categoria,
consolidada no período selecionado. `eixo` assume `sexo`, `raca_cor`,
`escolaridade` ou `faixa_etaria`. O campo de sexo descreve o registro de origem,
sem inferir identidade de gênero. Os códigos e grupos não informados permanecem
nos denominadores; códigos inesperados mantêm seu valor e recebem rótulo
`Código não mapeado`.

- `participacao_admissoes_pct`: admissões da categoria / admissões do mesmo
  recorte de UF, localidade e seção, vezes 100; nula quando não há admissões.
- `salario_medio_recorte`: média ponderada de todas as categorias daquele eixo
  e recorte, usando apenas salários de admissão positivos.
- `diferenca_salarial`: média da categoria − média do recorte.
- `diferenca_salarial_pct`: diferença / média do recorte, vezes 100; nula quando
  não há referência válida.

O mesmo evento participa uma vez de cada eixo. Não somar contagens entre eixos.
Para cruzamentos simultâneos, consultar `fct_perfil_mensal` com
`dim_perfil_demografico`; não juntar os quatro resultados marginais entre si.

## Repasse para o Marco 1

- **Euller:** acrescentar os testes genéricos aos modelos já descritos em
  `_gold__models.yml`: unicidade das chaves e grãos compostos, integridade das
  FKs e invariantes das métricas. Os testes de negócio temporários estão em
  `tests/test_gold.py`. O ADR-0005, diagrama e página analítica ficam com ele.
- **Davi:** os modelos usam `ref()` e aparecem no `manifest.json` do mesmo
  projeto; materializar após a Silver e antes de abrir o banco para consumo.
- **Arthur e Yan:** consultar as três fatos mensais ou a fato detalhada com
  suas dimensões. Os SQLs compilados são exemplos executáveis para o dashboard.
  O contrato CBO preserva os códigos textuais de seis dígitos para integração.

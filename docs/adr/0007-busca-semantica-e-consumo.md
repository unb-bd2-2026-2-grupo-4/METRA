# 0007 - Integrar busca de ocupações e linguagem natural ao catálogo de métricas

- **Status:** proposto
- **Data:** 29/10/2026
- **Responsáveis:** Euller Júlio e Arthur Evangelista.

## 1. Contexto

A E4 da equipe prevê busca semântica de ocupações e uma interface Text-to-SQL no Streamlit. Em 29/10, as branches consultadas contêm a Silver, mas não `src/app/dashboard.py`, índice vetorial ou modelos Gold. Implementar uma integração sobre tabelas e APIs presumidas criaria um contrato paralelo ao trabalho dos colegas.

A busca precisa retornar códigos CBO existentes e permitir aplicar esses códigos aos indicadores. A resposta em linguagem natural deve usar as mesmas definições de métricas do painel, sem inferir taxa de turnover sem estoque nem probabilidade individual de recolocação. A busca vetorial é um complemento da equipe: não substitui os requisitos oficiais de camada semântica, controle de acesso e ETL reverso da [E4](https://unb-bd2.github.io/PlanoEnsino/projeto/e4/).

## 2. Alternativas consideradas

### A. Filtros e busca textual por código/título — opção nula

Uma lista de ocupações e consultas parametrizadas cobre indicadores conhecidos com comportamento previsível. Serve de referência para medir se os embeddings melhoram consultas por sinônimos. Não resolve toda pergunta livre nem similaridade semântica.

### B. Embeddings de títulos/sinônimos e intenções limitadas ao catálogo

A busca ranqueia ocupações; a interface em linguagem natural identifica métrica, filtros e dimensões e usa consultas parametrizadas aprovadas. Limita cobertura, mas facilita explicar a fórmula e validar a resposta. É a primeira etapa proposta para integrar sem liberar SQL arbitrário.

### C. Embeddings e SQL livre gerado por modelo

Oferece maior flexibilidade, mas exige avaliação de correção, custo, latência, proteção do banco e limites de execução. Uma consulta `SELECT` ainda pode ler arquivos externos ou produzir carga excessiva. Uma conexão somente leitura, isoladamente, não define todas as permissões. Não escolher provedor, modelo pago ou enviar microdados sem decisão explícita da equipe.

## 3. Medição e Prototipação

**Ainda não há medições de busca ou Text-to-SQL.** Nenhum índice, embedding, chamada a LLM ou painel foi implementado nesta antecipação. O protocolo abaixo é o trabalho a executar quando Arthur e Tiago entregarem as interfaces.

| Experimento | Método | Critério proposto para revisão |
|---|---|---|
| Busca por sinônimo | Conjunto versionado de pelo menos 20 consultas em português e códigos esperados, revisado pela equipe | Comparar acerto entre os 5 primeiros resultados contra busca textual; nenhum código inexistente |
| Código exato | Buscar códigos de 6 dígitos, inclusive com zero inicial | Código correto em primeiro lugar |
| Resposta de indicador | Pelo menos uma pergunta de cada P1–P5 e casos ambíguos; comparar com SQL de referência | Igualdade dos valores e filtros nas perguntas suportadas; esclarecimento/recusa nas não suportadas |
| Latência | Mesma máquina e corpus, aquecimento e repetições registrados | Medir mediana/p95; definir meta com a equipe antes de aprovar |
| Restrições | Tentativas de escrita, leitura externa, múltiplas instruções e consulta excessiva | Não executar operações fora do catálogo; não expor registros individuais |

O resultado deve registrar versão/hash da CBO, modelo e revisão dos embeddings, dimensão dos vetores, métrica de distância, custo e versão do catálogo. Títulos genéricos de códigos não oficiais precisam aparecer identificados, para não sugerir uma descrição oficial inexistente.

## 4. Decisão

**Propor integração incremental da busca CBO com consultas controladas pelo catálogo de métricas, avaliando SQL livre apenas após comprovar correção e restrições.** A equipe ainda precisa aprovar essa abordagem; uma interface de intenções e templates não deve ser apresentada como Text-to-SQL irrestrito.

### Contrato proposto para implementação conjunta

1. **Busca:** receber texto e limite; retornar `codigo_cbo` textual de 6 dígitos, título, pontuação, indicador de cadastro oficial e versão do índice. Pontuação de similaridade não é probabilidade de emprego.
2. **Catálogo:** usar definições únicas de admissões, desligamentos, saldo e salário de admissão, além dos filtros permitidos. Nomes físicos das tabelas dependem da Gold real.
3. **Consulta:** o tradutor produz intenção, filtros e dimensões ou SQL candidato. Nenhuma resposta do modelo é executada diretamente. Filtros entram como parâmetros; identificadores são escolhidos de uma lista aprovada.
4. **Execução:** abrir o arquivo definido por `METRA_DUCKDB` somente para leitura e restringir o processo às relações/colunas de consumo aprovadas. Se SQL livre for adotado, validar a árvore sintática, funções e referências; bloquear leitura externa, extensões, anexação e escrita; impor prazo, memória e limite de resultado.
5. **Painel:** mostrar interpretação, filtros, competência coberta, fórmula e resultado agregado. Informar quando faltar denominador, quando houver ambiguidade ou quando a consulta não for suportada.
6. **Histórico CBO:** buscar uma representação por código da versão atual do catálogo; ao consultar uma fato com SCD, mapear o código para as versões correspondentes sem duplicar movimentos.

## 5. Consequências e Tradeoffs

### O que se ganha

- Resultados rastreáveis a códigos e métricas já verificáveis por SQL.
- Possibilidade de medir ganho da semântica contra uma busca simples.
- Integração gradual, sem tornar a geração livre de SQL pré-requisito para o painel.

### O que se perde ou se compromete

- Cobertura inicial limitada às intenções e filtros documentados.
- Construção de conjunto de avaliação e revisão das respostas pelos integrantes.
- Novo ciclo de atualização do índice sempre que o catálogo CBO mudar.

### O que restringe o sistema futuro

Mudança de modelo de embeddings exige reindexação e nova avaliação. Mudança de métrica ou schema exige revalidar painel e consultas em linguagem natural. Perguntas e logs não devem registrar dados pessoais ou credenciais; retenção e acesso ainda precisam de decisão de governança.

## 6. Gatilho de Revisão

Revisar se a busca semântica não superar a referência textual no conjunto acordado, se qualquer resposta divergir do SQL de referência, se surgirem códigos inexistentes ou se o executor permitir uma operação fora do catálogo. Não promover a proposta a aceita antes de existir evidência funcional de integração, correção e acesso.

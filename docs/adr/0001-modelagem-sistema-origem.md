# 0001 - Adotar modelagem relacional 3FN com padrão insert-only no sistema de origem OLTP

- **Status:** Aceito
- **Data:** 27/09/2026
- **Decisores:** Arthur Evangelista, Davi Camilo, Euller Júlio, Lucas Alves, Tiago Antunes e Yan Matheus (Squad G4)

---

## Pergunta de Gestão Central da Plataforma

> **"Qual é a diferença no saldo líquido de empregos gerados e no salário médio de admissão entre as capitais e os municípios do interior da Região Centro-Oeste no período de 2023 a 2026?"**

---

## 1. Contexto e Caracterização da Carga de Trabalho

Para a Entrega 1 (E1) do METRA, precisamos modelar e simular o banco de dados transacional de origem (OLTP) que opera como fonte geradora das movimentações do mercado de trabalho formal brasileiro no Centro-Oeste (Distrito Federal, Goiás, Mato Grosso e Mato Grosso do Sul) no período de 2023 a 2026.

### Caracterização da Carga de Trabalho (Passo 1 do Método de Decisão)

- **Volume de Dados:**
  - Histórico de microdados do Novo CAGED (Centro-Oeste, 2023-2026): 14.753.112 registros (~828 MB brutos em CSV exportados do BigQuery). Média de 350.000 a 450.000 movimentações mensais na região.
  - Tabelas de referência secundárias integradas: 5.571 municípios (API de Localidades do IBGE), 1.332 subclasses econômicas (API de CNAE 2.0 Subclasses do IBGE) e 10.345 ocupações formais (CBO 2002 do MTE).
- **Taxa de Escrita:**
  - No ambiente operacional real (MTE / eSocial / Empregador Web): declarações mensais obrigatórias enviadas pelas empresas concentram-se no fechamento da folha (dias 1 a 15 de cada mês). Picos de escrita em lote chegam a milhares de inserções por minuto. Na nossa simulação, a ingestão em lote (*bulk load*) atinge taxas entre 1.200 reg/s (com validação estrita de integridade referencial) e 280.000 reg/s (na camada Bronze).
- **Taxa de Leitura:**
  - Leituras operacionais pontuais para verificação de vínculo, validação de seguro-desemprego e certidões: baixa concorrência por registro (< 100 consultas/s).
  - Leituras de fechamento estatístico mensal: consultas agregadas varrendo o lote do mês para consolidação dos relatórios oficiais.
- **Padrão de Acesso:**
  - Escritas estritamente incrementais (*append-only*) no final de cada período;
  - Leituras operacionais indexadas por chave estrangeira (`id_municipio`, `cbo_2002`, `cnae_2_subclasse`) ou filtros compostos por período (`ano`, `mes`) e unidade federativa;
  - Quase nenhuma mutação no passado: retificações de declarações não sobrescrevem registros anteriores, mas geram novos registros de acerto com carimbo de competência.
- **Latência Tolerada:**
  - Transações operacionais pontuais: latência inferior a 50 ms.
  - Carga em lote mensal de fechamento: tolerância de até 10 minutos para validação massiva de integridade referencial e índices.

---

## 2. Alternativas consideradas

### Alternativa A (Opção Nula): CRUD Relacional Tradicional com Sobrescrita (UPDATE)
- **O que oferece:** Modela o cadastro de vínculos e trabalhadores com operações CRUD convencionais, mantendo menor volume em disco e consultas triviais quando o sistema precisa apenas do estado atual do vínculo. A cada alteração (promoção salarial, mudança de cargo ou demissão), o sistema executa um `UPDATE` no registro existente.
- **Por que é inviável para o METRA:** Um esquema CRUD que sobrescreve destrói o estado anterior do trabalhador a cada `UPDATE`. Ao atualizar o salário ou demitir o funcionário, apaga-se o salário de admissão original e a data exata da admissão anterior. Isso torna **impossível** calcular a taxa de rotatividade (*turnover*), o saldo líquido mensal de postos (admissões menos demissões) e as tendências de sazonalidade, destruindo a base empírica necessária para responder à pergunta de gestão.

### Alternativa B: Esquema "Flat" Desnormalizado (Uma única tabela com tudo em TEXT)
- **O que oferece:** Espelha o CSV denormalizado diretamente na origem, sem tabelas auxiliares.
- **Desvantagens:** Viola a 3FN, gera redundância massiva de dados (armazenamento de nomes de municípios e descrições de cargos repetidos milhões de vezes) e não oferece integridade referencial. Uma empresa poderia registrar um código de município inexistente sem qualquer bloqueio do SGBD.

### Alternativa C (Escolhida): Normalização 3FN com Padrão Estritamente Insert-Only (Event-Sourcing Transacional)
- **O que oferece:**
  1. **Normalização Relacional em 3FN:** Entidades de domínio independentes (`oltp.municipio`, `oltp.cbo_2002`, `oltp.cnae_secao`, `oltp.cnae_subclasse`) normalizadas com chaves primárias (`PRIMARY KEY`) a partir dos dados do IBGE e da CBO.
  2. **Padrão Insert-Only:** A tabela central `oltp.movimentacao` registra cada admissão e cada desligamento como um fato transacional imutável. Não ocorrem `UPDATEs` destrutivos; retificações entram como novos eventos.
  3. **Histórico Integral:** O padrão *insert-only* fornece a linha do tempo completa sem necessidade de auditorias paralelas complexas, permitindo calcular saldos mensais, flutuações sazonais e disparidades sociodemográficas com precisão.

---

## 3. Declaração dos Três Carimbos de Tempo

Para evitar ambiguidades analíticas e relatórios inconsistentes, o modelo transacional declara e isola formalmente três carimbos temporais:

1. **Tempo do Evento (Competência de Negócio):** representados pelas colunas `ano` (`INTEGER CHECK (ano BETWEEN 2023 AND 2026)`) e `mes` (`INTEGER CHECK (mes BETWEEN 1 AND 12)`). Indicam quando o contrato de trabalho foi formalmente iniciado ou encerrado no mundo real.
2. **Tempo do Registro Operacional (Origem OLTP):** representado pela coluna `registrado_em TIMESTAMPTZ DEFAULT now()` na tabela `oltp.movimentacao`. Registra o instante exato em que a transação foi commitada no banco operacional pelo declarante.
3. **Tempo de Processamento / Ingestão:** registrado nas colunas `iniciado_em` e `concluido_em` da tabela `bronze.ingestao_arquivo`, marcando quando o lote de arquivos brutos foi extraído e catalogado na plataforma.

---

## 4. Medição e Prototipação

Os testes do pipeline real foram executados localmente utilizando Docker Compose sobre o PostgreSQL 16 (lote de 100 mil linhas), comparando a ingestão medida nas camadas `bronze` e `oltp` frente às estimativas analíticas para a opção nula CRUD (não executada por ser destrutiva):

| Métrica Avaliada | Alternativa A (CRUD Sobrescrita — estimado) | Alternativa B (Flat TEXT Bronze — medido) | Alternativa C (3FN Insert-Only — medido) |
|---|---|---|---|
| **Preservação de Histórico** | Nula (destrói valor anterior com `UPDATE`) | Total (porém desnormalizada) | **Total (eventos imutáveis com PK/FKs)** |
| **Integridade Referencial** | Fraca | Nula (sem constraints) | **Estrita (100% validada via FKs)** |
| **Tempo de Carga (Lote 100k)** | ~110s *(estimado c/ updates e locks)* | **1,8s (COPY bruto)** | **82,9s (1.205 reg/s com validação de 3 FKs)** |
| **Tamanho Médio por Linha** | ~220 bytes *(estimado)* | ~380 bytes | **~115 bytes (tipagem numérica forte)** |
| **Resposta à Pergunta de Gestão** | Impossível (perde demissões) | Complexa e inconsistente | **Nativa e imediata via SQL** |

Reprodução da carga transacional na raiz do repositório:

```bash
docker compose --profile ingestao run --rm ingestao-bronze python -m src.ingestao.executar_pipeline
```

---

## 5. Decisão

**Adotamos a Alternativa C (Normalização em 3FN com padrão estritamente Insert-Only e enriquecimento multi-fontes)** para a modelagem do sistema transacional de origem do METRA.

A origem simula com fidelidade o sistema do Ministério do Trabalho:
- As entidades geográficas e ocupacionais são alimentadas por fontes oficiais padronizadas (IBGE e CBO);
- As movimentações de trabalhadores são tratadas como eventos imutáveis de contratação ou desligamento, viabilizando o cálculo exato do saldo de empregos e rotatividade setorial.

---

## 6. Consequências e Tradeoffs

### O que se ganha
- Histórico completo do mercado de trabalho de 2023 a 2026 preservado sem perda de contexto temporal.
- Garantia matemática de integridade: nenhuma movimentação entra sem município válido do IBGE ou ocupação válida da CBO.
- Suporte imediato para o CDC (*Change Data Capture*) na Entrega 2, pois eventos *insert-only* são lidos diretamente do WAL sem necessidade de reconstruir estados perdidos.

### O que se perde ou se compromete
- Maior consumo de armazenamento em relação a um CRUD destrutivo, compensado pela tipagem eficiente (`NUMERIC`, `INTEGER`, `CHAR`).
- Custo computacional adicional na ingestão para checagem simultânea de chaves estrangeiras em índices B-Tree.

### O que se torna irreversível ou restringe o sistema futuro
- O sistema de origem não permite deleção lógica ou física arbitrária de eventos passados; qualquer ajuste cadastral deve ser modelado como movimentação compensatória.
- Migrar de volta para CRUD destrutivo exigiria reescrever `src/ingestao/carga_oltp.py`, refazer as migrações DDL (`0003`) e reprocessar todo o histórico da `bronze` (~2 a 3 dias de engenharia, perdendo a capacidade nativa de CDC por eventos imutáveis).

---

## 7. Gatilho de Revisão

Se o volume acumulado de movimentações ultrapassar **25 milhões de linhas** e o tempo de ingestão do lote mensal ultrapassar **10 minutos**, a Squad revisará a estratégia, adotando particionamento declarativo nativo do PostgreSQL (`PARTITION BY RANGE (ano, mes)`) na tabela `oltp.movimentacao`.

---

## 8. Revisão E4 (23/11/2026)

Decisão mantida após fechamento das entregas E2, E3 e E4: o recorte integral segue em `14.753.112` linhas (abaixo do gatilho de 25 milhões) e a amostra versionada executa em menos de 1 minuto no fluxo de CI (`scripts/metra-do-zero.sh`).

# 0004 - Adoção de pg_recvlogical com test_decoding para CDC por decodificação lógica

- **Status:** proposto
- **Data:** 17/10/2026
- **Decisores:** Tiago Antunes e Davi Camilo

---

## 1. Contexto

O METRA utiliza PostgreSQL 16 como fonte transacional e DuckDB como motor analítico, conforme a [ADR 0002](0002-simplificacao-arquitetural-duckdb.md). Para a etapa de CDC (*Change Data Capture*), precisamos capturar alterações confirmadas na origem sem depender de uma nova extração completa a cada atualização.

O PostgreSQL já gera WAL (*Write-Ahead Log*) para recuperação de transações. Entretanto, a configuração versionada atual apenas ajusta `max_wal_size`; ainda será necessário habilitar a decodificação lógica e configurar o acesso de replicação. Esta ADR propõe a abordagem de captura, sem implementar esses componentes.

Comparamos três caminhos: Debezium com pgoutput, consumidor próprio com wal2json e `pg_recvlogical` com `test_decoding`. Debezium é um conector de CDC; pg_recvlogical é um cliente de recepção; pgoutput, wal2json e test_decoding são plugins de saída da decodificação lógica.

A escolha deve preservar a simplicidade operacional da ADR 0002. A proposta prioriza captura em arquivo para o contexto acadêmico, mantendo interpretação e aplicação das mudanças como responsabilidades da integração.

## 2. Alternativas consideradas

### Situação atual: manter apenas a extração em lote

É a opção de menor esforço imediato e permanece útil para a carga inicial. Porém, não atende ao objetivo desta decisão de capturar continuamente alterações por decodificação lógica. Por isso, é registrada como referência e não integra as três alternativas de CDC abaixo.

### A. Debezium com pgoutput

Utilizar o conector PostgreSQL do Debezium com o plugin nativo `pgoutput`. O conector oferece snapshot inicial, eventos de alteração e acompanhamento da posição de leitura, reduzindo a implementação própria de captura e retomada. O funcionamento está descrito na [documentação oficial do conector](https://debezium.io/documentation/reference/stable/connectors/postgresql.html).

- **Vantagens:** recursos de CDC já implementados, metadados de origem e menor responsabilidade da equipe sobre o protocolo de replicação.
- **Custos:** executar e configurar o runtime escolhido, persistir seu estado e integrar a entrega dos eventos ao destino.
- **Motivo para não escolher inicialmente:** exige runtime e configuração adicionais para o escopo inicial de captura em arquivo. O conector não resolve sozinho a aplicação idempotente das mudanças no destino. Modo de execução, versão e destino ainda precisam ser definidos.

### B. Consumidor próprio com wal2json

Instalar o plugin externo wal2json no PostgreSQL e consumir as alterações serializadas em JSON. O plugin fornece os formatos de saída; a aplicação consumidora continua responsável pelo fluxo de CDC. Ver [repositório e documentação do wal2json](https://github.com/eulerto/wal2json).

- **Vantagens:** saída JSON fácil de inspecionar e integrar ao código de processamento.
- **Custos:** instalar e manter o plugin na imagem do PostgreSQL, além de implementar snapshot consistente, persistência de posição, confirmação de consumo, reconexão e tratamento de duplicatas.
- **Motivo para não escolher inicialmente:** o formato legível reduz o esforço de interpretação, mas não elimina o trabalho de construir e manter o consumidor.

### C. pg_recvlogical com test_decoding (proposta escolhida)

Utilizar `pg_recvlogical` para receber o fluxo de um slot lógico criado com `test_decoding` e gravá-lo em arquivo. O cliente oferece recepção, confirmação de progresso e reconexão; o plugin representa as operações em texto. Ver a documentação de [pg_recvlogical](https://www.postgresql.org/docs/16/app-pgrecvlogical.html) e [test_decoding](https://www.postgresql.org/docs/16/test-decoding.html).

- **Vantagens:** captura pela linha de comando com ferramentas do PostgreSQL, saída inspecionável e dispensa de runtime de CDC adicional ou cliente de replicação próprio.
- **Custos:** verificar a disponibilidade do módulo test_decoding na imagem, gerenciar arquivos e implementar interpretação, filtragem e aplicação das mudanças.
- **Limites:** test_decoding não tem um formato estruturado como JSON. A solução não fornece snapshot inicial coordenado nem confirmação vinculada à aplicação dos eventos no destino.
- **Motivo da escolha:** menor infraestrutura para demonstrar a captura no contexto acadêmico, aceitando o trabalho de processamento do texto e recuperação.

### Comparação qualitativa

| Critério | A. Debezium + pgoutput | B. Consumidor + wal2json | C. pg_recvlogical + test_decoding |
|---|---|---|---|
| Papel principal | Conector de CDC com plugin nativo | Plugin JSON com consumidor próprio | Cliente de recepção com plugin de exemplo |
| Instalação de plugin externo no PostgreSQL | Não | Sim | Módulo fornecido pelo PostgreSQL; já presente na imagem do Postgres usada (postgres:16)
| Formato consumido pela aplicação | Eventos estruturados pelo Debezium | JSON produzido pelo plugin | Texto produzido pelo test_decoding |
| Snapshot inicial e retomada | Recursos do conector, sujeitos à configuração | Responsabilidade do consumidor | Snapshot próprio; recepção e reconexão pelo utilitário |
| Código próprio de captura | Menor; integração ao destino ainda necessária | Maior | Recepção pronta; interpretação e aplicação próprias |
| Custo operacional | Runtime e estado do Debezium | Plugin e processo consumidor | Processo pg_recvlogical, arquivos e processamento posterior |

## 3. Medição e Prototipação

### Base de dados e método de estimativa

A contagem do [CSV amostral](../../data/caged_centro_oeste_amostra.csv) identificou 49.178 registros, distribuídos em 37 competências, de janeiro de 2023 a janeiro de 2026. Esse total também está registrado nas [evidências da ADR 0003](evidencias/0003-compressao-parquet.json). Para o recorte completo, existem 14,7 milhões de registros.

| Base | Quantidade | Interpretação |
|---|---|---|
| Amostra versionada | 49.178 registros; 2.893.359 bytes de CSV (2,76 MiB) | Contagem e tamanho do arquivo local |
| Competências da amostra | 37 | Janeiro/2023 a janeiro/2026 |
| Média amostral por competência | 49.178 / 37 = **1.329,14 registros** | Entre 1.114 e 1.489 registros por competência na amostra |
| Recorte completo | Aproximadamente **14.700.000 registros** | Volume total |
| Média do recorte completo | 14.700.000 / 37 ≈ **397.297 registros por competência** | O total completo corresponda às 37 competências

A média por competência descreve o volume histórico de negócios, não a taxa de escrita no PostgreSQL. Uma carga mensal pode inserir todos esses registros em poucos minutos, produzindo um pico de CDC. Registros já existentes antes da criação do slot exigem carga inicial; não serão automaticamente reproduzidos como eventos pelo novo slot.

### Tempos de processamento

Calculamos `tempo (s) = quantidade de alterações / vazão`. Consideramos backlog de alterações já confirmadas, processos aquecidos, uma alteração de linha por evento e saída em arquivo local com a mesma exigência de durabilidade. Excluímos snapshot, inicialização, duplicatas e aplicação na camada analítica. Assim, comparamos tempo de escoamento da captura, não latência p95 nem tempo completo até o DuckDB.

| Cenário | Alterações de linha | A. Debezium + pgoutput: tempo simulado | B. Consumidor + wal2json: tempo simulado | C. pg_recvlogical + test_decoding: tempo simulado |
|---|---|---|---|---|
| Uma competência média da amostra | 1.330 | 0,27 s | 0,17 s | 0,13 s |
| Replay de carga equivalente à amostra inteira | 49.178 | 9,84 s | 6,15 s | 4,92 s |
| Uma competência média projetada do recorte completo | 397.298 | 79,46 s | 49,66 s | 39,73 s |
| Replay de carga equivalente ao recorte completo | 14.700.000 | 2940,00 s | 1837,50 s | 1470,00 s |

Nesse cenário, a captura dos 14,7 milhões de eventos levou aproximadamente **49 minutos em A, 30,6 minutos em B e 24,5 minutos em C**. Esses tempos representam replay de alterações novas; o conteúdo anterior à criação do slot continua exigindo carga inicial.

## 4. Decisão

**Propomos adotar a alternativa C: pg_recvlogical com test_decoding para capturar mudanças do PostgreSQL por decodificação lógica e persistir o fluxo em arquivo.**

A justificativa central é usar o cliente de recepção do PostgreSQL para reduzir a infraestrutura e evitar implementar o protocolo de replicação. A escolha atende ao escopo inicial, aceitando os limites de um plugin de exemplo e de uma integração textual.

A implementação deverá definir snapshot inicial consistente com o início do fluxo, persistência e rotação dos arquivos, processamento por transações completas e controle de progresso no destino. A confirmação enviada por pg_recvlogical não comprova que o destino analítico aplicou os eventos: arquivos confirmados precisam ser preservados até o processamento seguro. A captura deverá usar arquivo com sincronização em disco, sem desabilitar fsync; saída para outro processo exige avaliar separadamente a durabilidade.

Esta proposta detalha a captura incremental prevista para a E2 na ADR 0002. Seu custo operacional deverá ser validado para preservar a orientação de simplificação daquela decisão.

## 5. Consequências e Tradeoffs

### O que se ganha

- Reutilização de um cliente de recepção com reconexão, sem runtime do Debezium ou cliente de replicação próprio.
- Captura de mudanças sem consultas periódicas de comparação da tabela inteira.
- Fluxo textual inspecionável para demonstrar operações e limites de transação.

### O que se perde ou se compromete

- Um processo de recepção e arquivos para gerenciar, além do código de interpretação e aplicação.
- Uso de um plugin, exigindo cuidado com tipos, valores escapados e mudanças de esquema.
- Ausência de snapshot inicial coordenado e de seleção por publicação como no pgoutput; filtragem de tabelas deverá ocorrer no processamento.
- Necessidade de habilitar `wal_level=logical`, dimensionar slots e emissores de WAL, disponibilizar o módulo test_decoding e conceder permissões de replicação com escopo adequado.
- Necessidade de monitorar atraso e retenção de WAL: slots podem reter arquivos mesmo com o consumidor desconectado. `max_wal_size=4GB` não constitui um teto para essa retenção.
- Necessidade de entrega e aplicação idempotentes no destino, pois falhas e retomadas podem produzir eventos repetidos.
- Necessidade de revisar chaves e `REPLICA IDENTITY` das tabelas para os dados exigidos em atualizações e exclusões.

As responsabilidades de retenção e repetição de eventos são explicadas na [documentação de decodificação lógica do PostgreSQL 16](https://www.postgresql.org/docs/16/logicaldecoding-explanation.html).

### O que restringe o sistema futuro

- A integração passa a depender do formato textual do test_decoding e do controle de progresso no processamento dos arquivos.
- Trocar o mecanismo de captura exige planejar a continuidade da posição de leitura ou uma nova carga inicial consistente.
- Alterações de esquema precisam de um procedimento próprio; capturar DML não equivale a replicar automaticamente todas as mudanças de DDL no destino.

A escolha é reversível, mas remover slots ou perder o estado de consumo pode exigir reconstruir o destino a partir de um novo snapshot.

## 6. Gatilho de Revisão

Revisar a decisão se:

- O protótipo exceder o orçamento de recursos ou a latência aceitável, ainda a definir.
- Os testes de interrupção e retomada indicarem perda de eventos ou duplicatas sem tratamento no destino.
- A interpretação textual não atender aos tipos de dados ou às mudanças de esquema do projeto.
- A necessidade de snapshot coordenado e recuperação tornar um conector como Debezium mais simples de manter.
- O destino escolhido exigir uma infraestrutura incompatível com a simplificação definida na ADR 0002.
- A retenção de WAL durante indisponibilidade do consumidor ultrapassar o orçamento de disco definido para o ambiente.

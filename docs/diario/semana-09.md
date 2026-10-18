# Diário de Bordo - Semana 09

- **Data:** Semana 9 (Semestre 2026/2)
- **Autor(es):** Davi Camilo, Tiago Antunes e Arthur Evangelista (com apoio da Squad G4, registrado no `uso-de-ia.md`)

---

## O que foi medido e analisado

- **Avaliação de mecanismos de CDC para o PostgreSQL 16 (ADR 0004):** Comparação técnica e operacional entre três alternativas de captura de mudanças a partir do WAL (*Write-Ahead Log*): Debezium com `pgoutput`, consumidor próprio com `wal2json` e utilitário nativo `pg_recvlogical` com o plugin `test_decoding`, além da opção nula de recarga periódica em lote.
- **Estimativa de vazão e escoamento de backlog:** Projeção do tempo de captura para uma competência média da amostra (1.330 linhas em 0,13 s com `pg_recvlogical`), para a amostra completa (49.178 linhas em 4,92 s) e para o recorte integral do Centro-Oeste (14,7 milhões de linhas em aproximadamente 24,5 minutos).
- **Prototipação de captura e replay idempotente (`src/cdc/`):** Execução prática dos scripts `01_preparar.sh`, `02_consumir.sh` e `03_testar.sh` sobre a tabela isolada `oltp.cdc_probe`, capturando transações confirmadas (`INSERT` no XID 769 e `UPDATE` no XID 770) em `data/cdc/eventos.log` e validando o reprocessamento com deduplicação em SQLite (`04_reprocessar.py`) e suíte de testes unitários (`tests/test_cdc_replay.py`).

## O que surpreendeu

- **Simplicidade do `pg_recvlogical` nativo frente a stacks pesadas de streaming:** A imagem oficial `postgres:16` já inclui o cliente `pg_recvlogical` e o plugin `test_decoding`, permitindo demonstrar a decodificação lógica real do WAL sem precisar subir clusters Kafka, ZooKeeper ou Kafka Connect.
- **Diferença de comportamento no fechamento de arquivos SQLite entre Linux e Windows:** O gerenciador de contexto padrão `with sqlite3.connect(...)` em Python confirma a transação, mas mantém o descritor de arquivo aberto, o que causava erro de bloqueio (`WinError 32`) ao limpar diretórios temporários de teste no Windows antes do uso explícito de `contextlib.closing`.

## O que foi decidido

- **Formalização do ADR 0004 e implementação do CDC com `pg_recvlogical`:** Habilitação de `wal_level=logical` no `docker-compose.yml` e adoção do slot lógico `metra_cdc_slot` com `test_decoding` para capturar alterações confirmadas sem sobrecarregar a arquitetura.
- **Garantia de idempotência no consumidor e descarte de transações incompletas:** Implementação do parser em `04_reprocessar.py` que processa exclusivamente blocos `BEGIN ... COMMIT` íntegros e calcula um hash SHA-256 determinístico (`evento_id`) persistido com `INSERT OR IGNORE`, assegurando que reexecuções sucessivas do mesmo log ou de janelas reprocessadas jamais dupliquem registros no destino.
- **Tratamento explícito de dado atrasado e reprocessamento de janela:** Documentação e cobertura por testes automatizados (`test_dado_atrasado_e_reprocessamento_janela`) demonstrando que eventos atrasados são incorporados sem perda nem duplicação das transações anteriores e roteados para a partição de competência (`ano`) correta na camada analítica.

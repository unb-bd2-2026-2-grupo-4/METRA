# Diário de Bordo - Semana 07

- **Data do registro:** 15/10/2026
- **Responsável pela tarefa:** Euller Júlio
- **Escopo deste registro:** comparação de compressão da E2, com implementação assistida por Codex; revisão humana pendente.

---

## O que foi medido e analisado

- Comparação de uncompressed, Snappy e Zstd sobre as 49.178 movimentações da amostra versionada, tipadas conforme o modelo OLTP e particionadas por ano. Os campos de linhagem foram reconstruídos explicitamente; não havia PostgreSQL ou Docker no ambiente para executar a extração real.
- Um aquecimento e sete rodadas válidas por codec, com ordem rotativa, uma thread e a mesma cópia da fonte. Foram medidos tamanho dos arquivos, tempo de escrita e leitura de todas as colunas, sem limpar o cache do sistema operacional.
- Uncompressed: 1.685.300 bytes, 55,715 ms de escrita e 20,742 ms de leitura. Snappy: 960.593 bytes, 56,731 ms e 18,913 ms. Zstd: 556.147 bytes, 82,367 ms e 35,132 ms. Os tempos são medianas; todas as rodadas constam na evidência vinculada ao [ADR 0003](../adr/0003-compressao-parquet.md).
- Verificação exata de schema e multiconjunto de linhas para cada codec, fora do cronômetro. Testes adicionais com campos vazios, salários negativos, códigos com zeros à esquerda e entradas inválidas.

## O que surpreendeu

- Zstd reduziu o espaço em mais 42,1% frente a Snappy, mas o custo combinado de escrita e leitura ficou 55,3% maior nesta execução. O menor arquivo não foi o vencedor pelo critério adotado.
- `count(*)` isolado não é uma medição suficiente de leitura Parquet: o motor pode responder pelos metadados. O benchmark usa hashes de todas as colunas para exigir sua leitura.

## O que foi decidido

- Manter Snappy como padrão e substituir a indicação de escolha provisória por uma referência à ADR 0003.
- Escolher o menor arquivo entre os codecs cuja soma das medianas de escrita e leitura não ultrapasse Snappy em mais de 25%. Esse é o critério do experimento, não um SLA do projeto.
- Preservar os números brutos, os comandos de reprodução e as limitações. Reavaliar a decisão com o OLTP completo e quando houver mudança de motor, hardware ou carga de consulta.
- Manter a implementação restrita ao benchmark, ADR, padrão de compressão e registros desta tarefa. A comparação não valida o escritor Delta nem substitui a ADR de ingestão da E2.

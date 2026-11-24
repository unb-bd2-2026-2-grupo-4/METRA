# Retrospectiva do ciclo de vida percorrido

Esse documento traz uma **retrospectiva** de todo o ciclo de desenvolvimento do METRA, de forma a analisar e relatar o macro do que foi feito e aprendido.

## Da pergunta de gestão aos dados de origem

O METRA começou com a pergunta sobre a diferença no saldo de empregos e no salário médio de admissão entre capitais e interior do Centro-Oeste. Ela orientou o recorte de municípios, competências e medidas que precisavam ser preservados até o consumo. A integração do Novo CAGED com municípios e atividades econômicas do IBGE e ocupações da CBO permitiu transformar códigos de fontes distintas em dimensões utilizáveis nas análises.

A separação entre Bronze e OLTP tornou explícitas as responsabilidades de preservar a entrada e aplicar tipos, chaves e regras de integridade. Os identificadores de ingestão e de linha mantiveram a possibilidade de voltar ao registro de origem. O aprendizado dessa etapa foi que decisões de carga e modelagem determinam quais perguntas poderão ser respondidas nas etapas seguintes.

## Da origem transacional ao armazenamento analítico

A extração em lote levou o histórico do PostgreSQL para Parquet, com conciliação das contagens e substituição atômica dos arquivos. Os experimentos de compressão e a adoção de armazenamento local ajudaram a adequar a arquitetura aos recursos disponíveis para a equipe e para a reprodução da entrega. A materialização Delta acrescentou o versionamento da tabela de movimentações, enquanto o experimento de CDC demonstrou captura e reprocessamento idempotente de eventos do WAL.

Os problemas de concorrência na escrita de arquivos reforçaram a necessidade de travas e diretórios temporários exclusivos. Passamos a tratar a recuperação de uma execução interrompida como parte do fluxo de dados.

## Do armazenamento às métricas

Com dbt e DuckDB, organizamos a Silver e a Gold em modelos com dependências e testes. Preservar o grão de movimentação permitiu manter recortes por ocupação e perfil demográfico, enquanto os agregados mensais atenderam às consultas recorrentes. O histórico SCD Tipo 2 da CBO acrescentou a dimensão temporal às alterações do catálogo de ocupações.

Os benchmarks mostraram que o benefício dos agregados depende da escala. Na base completa, a consulta avaliada passou de 33,27 ms na fato detalhada para 0,84 ms no agregado. A camada semântica compartilhada e os testes de paridade reduziram o risco de o painel e as análises calcularem a mesma métrica de formas diferentes. A divergência de precisão salarial na P5 também levou à revisão dos tipos usados na soma.

## Das métricas ao consumo e à governança

O Streamlit, a busca CBO e o Text-to-SQL aproximaram os indicadores das perguntas de gestão. O JSON exportado das views de consumo permitiu disponibilizar o painel e o agente no GitHub Pages. A revisão das interfaces revelou problemas que a validação isolada das tabelas deixava passar, como KPIs desalinhados aos filtros e meses sem grupos publicados tratados como zero na sazonalidade.

A governança passou a envolver também a escolha dos recortes expostos. A base de consumo isolada, a supressão de pequenos grupos e o tratamento das medidas salariais limitaram a exposição dos microdados. A auditoria registrou riscos residuais de inferência por diferença, e a demonstração de descarte tornou verificável parte do encerramento do ciclo de vida. O catálogo e a linhagem conectaram fontes, modelos e consumidores para apoiar a revisão dessas decisões.

## O que funcionou e o que melhoraríamos

- **Conciliação entre etapas.** Usar contagens, saldos e análises de referência ajudou a localizar divergências na transição entre as camadas. A amostra versionada deu uma base comum de reprodução para a equipe e para a avaliação.
- **Reprodutibilidade integrada.** O Compose, o Dagster e o CI passaram a verificar o caminho completo. O painel ficou condicionado ao sucesso do pipeline, aproximando a execução local do fluxo validado nos testes.
- **Decisões acompanhadas de medições.** Os ADRs reuniram alternativas, resultados e critérios de revisão. Repetir as medições em volumes diferentes evitou generalizar o desempenho observado na amostra.
- **Validação dos consumidores mais cedo.** Conferir conjuntamente filtros, KPIs, gráficos e respostas do agente desde as primeiras versões teria antecipado os ajustes encontrados no fechamento.
- **Evidência operacional desde a primeira publicação.** Registrar o vínculo entre lote, extração, hash e deploy desde o início facilitaria medir a meta de freshness. A documentação preserva o alcance das verificações realizadas e o estado do ensaio de conteúdo novo.

## Aprendizado do ciclo completo

O resultado do projeto reúne decisões que se propagam da fonte ao consumidor. A escolha do grão determina os recortes disponíveis, a definição das métricas determina a consistência das respostas e a política de publicação determina a exposição dos dados e o prazo de atualização. Percorrer essas etapas mostrou à equipe a importância de acompanhar cada transformação com contratos, conciliação, evidências e documentação das limitações observadas. Com isso, durante o desenvolvimento, foi possível aprender novos temas durante toda a disciplina.

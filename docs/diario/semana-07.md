# Diário de Bordo - Semana 07

- **Data:** Semana 7 (Semestre 2026/2)
- **Autor(es):** Squad G4 (Arthur Evangelista, Davi Camilo, Euller Júlio, Lucas Alves, Tiago Antunes e Yan Matheus)

---

## O que foi medido e analisado

- **Apresentação da Entrega 1 (E1) e avaliação da arquitetura:** Apresentação formal da fonte transacional OLTP em 3FN (`PostgreSQL 16`), das migrações versionadas e da carga reprodutível do Novo CAGED (Centro-Oeste, 2023 a 2026), acompanhada da revisão crítica da arquitetura completa da plataforma junto à professora.
- **Comparação de sobrecarga operacional (PostgreSQL + Stack Completa vs. DuckDB):** Medição do custo de memória RAM em repouso (~2.800 MB com múltiplos contêineres contra ~180 MB mantendo apenas o PostgreSQL e 0 MB em repouso no DuckDB *in-process*), tempo de inicialização e latência de agregação analítica sobre as 49.178 linhas da amostra (48 ms no PostgreSQL contra 1,8 ms no DuckDB vetorizado).
- **Validação da consulta central de gestão no DuckDB:** Prototipação e execução do módulo `src/analise.py`, conectando o DuckDB ao PostgreSQL em modo somente leitura para responder à pergunta central (comparação de saldo líquido de empregos e salário médio nominal de admissão entre capitais e interior).

## O que surpreendeu

- **Direcionamento docente para simplificação radical com DuckDB:** A professora destacou que manter serviços intermediários pesados (como emulação de S3 via MinIO e fluxos complexos de ETL reverso) gerava sobreengenharia desnecessária para o escopo analítico do projeto, recomendando usar o DuckDB diretamente para extração, processamento e apresentação dos dados.
- **Poluição visual na navegação da documentação:** A disposição anterior com 7 abas independentes no topo do portal MkDocs dificultava a localização dos artefatos de engenharia e governança durante a apresentação.

## O que foi decidido

- **Formalização do ADR 0002 (Simplificação Arquitetural com DuckDB):** Adoção de uma arquitetura híbrida pragmática que preserva o PostgreSQL 16 estritamente como fonte transacional OLTP (garantindo conformidade integral com a E1) e consagra o DuckDB como motor analítico vetorizado central para as entregas seguintes.
- **Implementação do módulo analítico local (`src/analise.py`):** Consolidação da leitura transacional `READ_ONLY` a partir do PostgreSQL para o DuckDB local, garantindo substituição atômica e cálculo exato dos indicadores sem arredondamento intermediário.
- **Reorganização do portal MkDocs e explicitação dos relacionamentos:** Agrupamento da navegação superior em 3 seções claras (*Visão Geral*, *Engenharia de Dados* e *Governança & Decisões*) e criação da página dedicada de relacionamento entre as bases (`docs/relacionamentos.md`).

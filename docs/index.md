# METRA (Monitoramento e Engenharia de dados do TRAbalho)

Bem-vindo à documentação oficial do **METRA** (Monitoramento e Engenharia de dados do TRAbalho), plataforma de engenharia de dados desenvolvida pela **Squad G4** para a disciplina de **Banco de Dados 2** (Engenharia de Software - FCTE/UnB).

---

## Membros da Squad

| Membro | Matrícula |
| :--- | :--- |
| **Arthur Evangelista** | 231027032 |
| **Davi Camilo** | 231011220 |
| **Euller Júlio** | 231026714 |
| **Lucas Alves** | 231027159 |
| **Tiago Antunes** | 231011838 |
| **Yan Matheus** | 231038303 |

---

## Objetivo do Projeto Integrado

O **METRA** materializa o **Projeto Integrado** da disciplina, integrando os quatro estágios do ciclo de vida do dado:

1. **Fonte Transacional (OLTP):** Modelagem relacional e carga a partir de dados públicos abertos.
2. **Ingestão e Armazenamento:** Captura de dados em lote e streaming analítico.
3. **Camada Analítica (OLAP):** Modelagem dimensional, testes de qualidade e transformações de dados.
4. **Consumo e Governança:** Painéis gerenciais para resposta às perguntas de gestão e conformidade de governança.

O recorte do projeto concentra-se no **Mercado de Trabalho Formal da Região Centro-Oeste** (Distrito Federal, Goiás, Mato Grosso e Mato Grosso do Sul), com microdados do **Novo CAGED** e tabelas de referência do **IBGE** e **CBO 2002**.

---

## Navegação Rápida na Plataforma

<div class="grid cards" markdown>

-   **[Domínio e Gestão](dominio.md)**
    
    ---
    
    Diagnóstico da rotatividade e assimetria do emprego formal no Centro-Oeste, personas atendidas e pergunta norteadora de gestão.

-   **[Arquitetura da Plataforma](arquitetura.md)**
    
    ---
    
    Estrutura técnica e visão do pipeline de dados, cobrindo o planejamento de E1 a E4.

-   **[Camada Bronze e Ingestão](camada-bronze.md)**
    
    ---
    
    Esquema físico para recepção de dados brutos, dicionário de campos e scripts de carga automatizados.

-   **[Relacionamento entre as Bases](relacionamentos.md)**
    
    ---
    
    Integração entre Novo CAGED, IBGE e CBO 2002, com mapeamento das chaves de relacionamento, cardinalidades e modelo de dados transacional.

-   **[Captura de Mudanças (CDC)](cdc.md)**
    
    ---
    
    Captura de alterações no PostgreSQL por decodificação lógica do WAL, propagação de eventos e reprocessamento idempotente com deduplicação.

-   **[Extração para Parquet e Delta](camada-parquet.md)**
    
    ---
    
    Extração dos dados transacionais para formatos analíticos abertos, com particionamento, compressão, validação de integridade e materialização em Delta Lake.

-   **[Decisões de Arquitetura (ADRs)](adr/0001-modelagem-sistema-origem.md)**
    
    ---
    
    Registros formais de decisões estruturais em 6 passos (ADR 0001: Origem Transacional e ADR 0002: Simplificação com DuckDB).

-   **[Governança e Uso de IA](uso-de-ia.md)**
    
    ---
    
    Declaração formal do uso ético de modelos de inteligência artificial generativa e rastreabilidade pedagógica.

-   **[Diário de Bordo](diario/semana-01.md)**
    
    ---
    
    Registros semanais de medições, descobertas empíricas e tomada de decisão ao longo do semestre.

</div>

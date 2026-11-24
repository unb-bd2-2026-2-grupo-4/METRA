# Diário de Bordo - Semana 13

- **Data:** Semana 13 (Semestre 2026/2)
- **Autor(es):** Squad G4 (Arthur Evangelista, Davi Camilo, Euller Júlio, Lucas Alves, Tiago Antunes e Yan Matheus)

---

## O que foi medido e analisado

- **Fluxo completo reproduzível:** Encadeamento da ingestão, extração Parquet, materialização Delta, transformações dbt e painel pelo Docker Compose. O verificador `src/qualidade/verificar_fluxo.py` concilia contagens e saldos entre as camadas. A execução documentada com a amostra utilizou 49.178 movimentações e saldo de +1.472 vínculos.
- **Testes de integração e CI:** Inclusão de testes sobre a Gold real para conciliar agregados e movimentações com o PostgreSQL, validar invariantes de municípios, salários e competências e comparar P1 a P5 com as análises dbt. O GitHub Actions passou a executar o fluxo do zero e a suíte automatizada.
- **Camada semântica de métricas:** Definição das sete métricas em `dbt_metra/models/semantic/metricas.yml` e implementação de um compilador Python em `src/metricas/camada_semantica.py`. Análises dbt, painel, busca CBO e Text-to-SQL passaram a consumir as definições compartilhadas, com testes de paridade e conciliação.

## O que surpreendeu

- **Inicialização do painel dependente do pipeline:** A disponibilidade do serviço não assegurava que a base analítica tivesse sido gerada e validada. O Compose passou a condicionar a inicialização do painel ao sucesso do fluxo.
- **Precisão no cálculo da P5:** A soma salarial em ponto flutuante apresentou divergência na nona casa decimal. A comparação com a Gold orientou o uso de `DECIMAL` para a soma.
- **Filtros de ocupação nos KPIs:** A revisão identificou que os indicadores de cabeçalho precisavam acompanhar o recorte por ocupação aplicado ao painel.

## O que foi decidido

- **Reproduzir e validar o projeto a partir da amostra:** Adotar `scripts/metra-do-zero.sh` e o fluxo de CI para reconstruir e verificar as camadas. O script documenta a remoção dos volumes e artefatos gerados antes da execução.
- **Centralizar as fórmulas das métricas:** Compartilhar as definições entre dbt e Python e conferir a paridade dos resultados, preservando somas e contagens válidas para recompor médias salariais ponderadas.
- **Alinhar os KPIs aos filtros:** Aplicar o mesmo recorte de ocupação às métricas e às visualizações do painel.

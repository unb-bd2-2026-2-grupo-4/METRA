# Diário de Bordo - Semana 12

- **Data:** Semana 12 (Semestre 2026/2)
- **Autor(es):** Squad G4 (Arthur Evangelista, Davi Camilo, Euller Júlio, Lucas Alves, Tiago Antunes e Yan Matheus)

---

## O que foi medido e analisado

- **Conciliação da P3 no painel:** Comparação da série anual de capitais e interior com as análises de referência, seguida do ajuste dos filtros de ano e UF. A análise deu continuidade à conciliação descrita na semana 11.
- **Evolução das visões interativas:** Inclusão de visualizações no Streamlit, complementação da matriz de fluxos e salários da P4 e adição do hiato salarial e do saldo líquido por perfil na P5.
- **Cobertura das cinco perguntas:** Criação de testes para as visões P1 a P5 em `tests/test_dashboard.py`, verificando as respostas e os filtros apresentados no painel.

## O que surpreendeu

- **Coerência entre filtros e indicadores:** A revisão das visões mostrou a importância de conferir os indicadores de cabeçalho junto aos gráficos, especialmente quando o recorte envolve ocupação. O ajuste dos KPIs foi concluído na semana seguinte.
- **Interpretação das medidas da P4 e da P5:** Comparações de fluxos e diferenças salariais precisaram ser apresentadas junto aos seus recortes para apoiar a leitura das perguntas de gestão.

## O que foi decidido

- **Consolidar as cinco perguntas no painel:** Manter as visões P1 a P5 com filtros e testes, incluindo a comparação de capitais e interior já conciliada com as análises de referência.
- **Aprimorar as análises de perfil e fluxos:** Exibir na P4 a matriz de equilíbrio de fluxos e salários e, na P5, o hiato salarial e o saldo líquido por perfil.

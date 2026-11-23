-- Competências do período, com tem_dados indicando movimentação na origem
-- (independentemente da supressão): mês sem dados não é zero observado.
select competencia, tem_dados
from {{ ref('dim_competencia') }}

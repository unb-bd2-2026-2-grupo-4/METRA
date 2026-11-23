-- Grade diária exigida pela validação da camada semântica do dbt (time spine).
-- Cobre o período publicado do METRA; as métricas são agregadas por competência (mês).
select cast(dia as date) as date_day
from range(date '2023-01-01', date '2027-01-01', interval 1 day) t(dia)

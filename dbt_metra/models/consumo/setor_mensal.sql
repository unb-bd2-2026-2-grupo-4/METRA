-- Fluxos por competência, UF e seção CNAE (P1, P2 e P4), sem grupos pequenos.
{{ publicar_grupos(ref('fct_setor_mensal'), ['competencia', 'sigla_uf', 'codigo_secao']) }}

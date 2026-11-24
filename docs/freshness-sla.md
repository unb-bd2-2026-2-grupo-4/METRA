# Freshness e SLA da publicação

A meta proposta da E4 é **publicar e validar o snapshot no GitHub Pages em até 24 horas corridas após a extração Parquet bem-sucedida do mesmo lote**. O prazo inclui materialização, testes, revisão do PR, merge, deploy e conferência do arquivo servido.

| Medida | Evidência |
| --- | --- |
| Cobertura do dado | Último mês observado em `calendario` com `tem_dados = true`. A amostra da E4 tem 37 competências observadas, de janeiro de 2023 a janeiro de 2026. |
| Extração concluída | Horário do evento de materialização bem-sucedida de `exportar_parquet` no run de `pipeline_metra`. |
| Snapshot local validado | Horário e `sha256` do evento de `exportar_json_consumo` no mesmo `run_id`, após as validações do exportador. O horário mede a disponibilidade local. |
| Publicação validada | Primeira conferência pública bem-sucedida do JSON com o mesmo SHA-256, após revisão, testes e deploy. Registrar também o commit ou a execução do workflow. |

A competência representa o mês de referência do Novo CAGED. Um reprocessamento pode gerar conteúdo novo para uma competência já observada ou repetir os mesmos bytes. O schedule `pipeline_metra_mensal` roda no dia 5 às 6h em `America/Sao_Paulo` quando habilitado com o daemon ativo. Ele atualiza o snapshot local. O workflow de deploy é disparado pelo push à `main`.

## Como verificar um lote

1. No run bem-sucedido de `pipeline_metra`, registre o `run_id`, o horário do evento de `exportar_parquet` e, a partir de `exportar_json_consumo`, o horário, a competência final e o `sha256`. A exportação isolada pelo job `exportar_json_consumo_job` precisa de um vínculo documentado com a extração de origem para entrar na medição.
2. Confirme a validação do PR e registre o commit da `main` e o deploy. Após o deploy, compare o arquivo servido pelo Pages com o hash do asset. O comando imprime o instante da verificação em UTC após o download e a validação. Substitua o valor de `sha256_dagster` pelo do run.

   ```bash
   (
     sha256_dagster='SHA256_DO_ASSET'
     snapshot_sla=$(mktemp) || exit 1
     trap 'rm -f "$snapshot_sla"' EXIT
     curl --fail --silent --show-error --location --max-time 30 \
         "https://unb-bd2-2026-2-grupo-4.github.io/METRA/assets/dados/metra.json?sla=$(date +%s)" \
         --output "$snapshot_sla" &&
         printf '%s  %s\n' "$sha256_dagster" "$snapshot_sla" | sha256sum --check &&
         date -u '+%Y-%m-%dT%H:%M:%SZ'
   )
   ```

3. Registre os horários com fuso e calcule `publicacao_validada_em - extracao_concluida_em`. Classifique como **dentro da meta** se a publicação for validada em até 24 horas. Se após 24 horas o hash esperado seguir indisponível ou diferente, registre o **atraso** e investigue em qual etapa o lote parou. Se a primeira verificação somente ocorrer fora da janela e já encontrar o hash, registre **prazo indeterminado** salvo evidência verificável de disponibilidade anterior. Um lote que repete o hash já servido pode ser registrado como **sem mudança**, com conferência do conteúdo e sem novo deploy.
4. Registre os lotes com execução falha, dados sem correspondência ou evidência incompleta com seu motivo. A E4 usa conferência operacional por lote. Os logs do Dagster, o PR e o histórico de deploy fornecem as referências para diagnosticar atrasos e repetir a verificação.

## Evidências

| Evento | Data e hora em Brasília | Referência |
| --- | --- | --- |
| Snapshot integrado à `main` | 23/11/2026 16:54:11 | `b1a4391`, merge do PR #20 |
| Commit de deploy com o mesmo snapshot | 24/11/2026 11:27:08 | `e2d2fc8` na `origin/gh-pages`, gerado a partir de `20d8b0c` |
| Conferência do JSON servido pelo Pages | 24/11/2026 11:37 | Download HTTP e SHA-256 idêntico ao snapshot versionado |

O intervalo entre a integração e o commit de deploy foi de **18h 32min 57s**. Os dois commits e o arquivo servido têm o mesmo SHA-256, `7582814fdae7da88cae63b6bcbba33dbe0ff313f1504d8920887df5034bc9487`. Esse hash corresponde aos bytes em LF. O benchmark da [ADR-0008](adr/0008-disponibilizacao-camada-semantica-e-json-pages.md) usou a cópia local em CRLF. Falta o `run_id` que associe esse snapshot publicado ao evento de extração, por isso o prazo ponta a ponta do lote fica **indeterminado**.

Para inspecionar a evidência a partir da raiz do clone:

```bash
git show -s --format='%h %cI %s' b1a4391 e2d2fc8
git show b1a4391:docs/assets/dados/metra.json | sha256sum
git show e2d2fc8:assets/dados/metra.json | sha256sum
```

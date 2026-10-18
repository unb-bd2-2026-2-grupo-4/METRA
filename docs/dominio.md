# Domínio e Perguntas de Gestão

## O Domínio

O domínio escolhido pela Squad G4 é o **Mercado de Trabalho Formal Brasileiro**, com foco nos dados de contratação, desligamento e remuneração registrados no **Novo CAGED** (Cadastro Geral de Empregados e Desempregados), complementados por tabelas auxiliares do **IBGE** (municípios e microrregiões) e do **MTE** (Classificação Brasileira de Ocupações — CBO 2002).

---

## O Problema

Trabalhadores que buscam emprego ou transição profissional encontram severas barreiras para identificar com precisão quando e onde a contratação com carteira assinada está aquecendo ou esfriando. Ao mesmo tempo, gestores públicos e pesquisadores de políticas de emprego carecem de ferramentas unificadas para mensurar discrepâncias salariais e de rotatividade segundo recortes de raça/cor, gênero, nível de instrução e faixa etária. Como resultado, decisões cruciais de recolocação ou de alocação de incentivos econômicos governamentais continuam sendo pautadas em percepções subjetivas.

---

## Personas

### 1. Trabalhador em Busca de Recolocação

- **Perfil:** Profissional desempregado ou empregado buscando mudar de área/empresa no Distrito Federal e regiões metropolitanas.
- **Necessidade:** Compreender quais setores econômicos estão em expansão líquida (saldo positivo de contratações), a sazonalidade dos processos seletivos e a faixa salarial real praticada para o seu nível de escolaridade e ocupação.

### 2. Gestor Público e Pesquisador de Políticas de Trabalho

- **Perfil:** Analista governamental ou pesquisador responsável por desenhar políticas ativas de emprego, combate ao desemprego e fomento à igualdade no mercado formal.
- **Necessidade:** Monitorar discrepâncias regionais entre polos urbanos e cidades do interior, identificar setores com alta rotatividade patológica (_turnover_) e detectar disparidades estruturais de gênero e raça para direcionar incentivos e fiscalizações.

---

## As 5 Perguntas de Gestão

O **METRA** tem como critério de sucesso a capacidade de responder de forma ágil, fundamentada e reproduzível às seguintes perguntas:

1. **Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?**  
   _Objetivo:_ Avaliar a dinâmica setorial local (serviços, comércio, construção civil, administração pública) e o saldo líquido de postos de trabalho.

2. **Existe sazonalidade evidente nas contratações e demissões?**  
   _Objetivo:_ Mensurar variações mensais sistemáticas (ex.: contratações temporárias no varejo no 4º trimestre e demissões subsequentes em janeiro).

3. **Qual é a disparidade no saldo de empregos formais entre as capitais e os municípios do interior?**  
   _Objetivo:_ Entender a concentração geográfica das vagas e a capacidade de geração de empregos fora dos grandes centros urbanos.

4. **Setores econômicos com maior taxa de rotatividade (_turnover_) praticam salários médios menores?**  
   _Objetivo:_ Analisar a correlação empírica entre precarização/volatilidade do vínculo empregatício e remuneração média de admissão.

5. **Como o perfil sociodemográfico (gênero, raça/cor, idade, escolaridade) impacta o nível salarial e as chances de recolocação?**  
   _Objetivo:_ Evidenciar gaps de renda e oportunidades no mercado formal, gerando insumos para políticas de equidade e inclusão social.

---

## Fontes de Dados e Justificativas Técnicas

Veja [Relacionamento entre as bases](relacionamentos.md) para os campos que conectam essas fontes: código do município, código CBO e subclasse CNAE.

- **Novo CAGED (Microdados de Estabelecimentos e Movimentações):** Disponibilizado pelo Ministério do Trabalho e Emprego (via Base dos Dados). Provê a granularidade de cada admissão e demissão individual com carimbo de tempo mensal e dados cadastrais do empregador.
- **IBGE (Malha Municipal):** Fornece a chave geográfica padronizada para agregações espaciais e distinção entre capitais e municípios do interior.
- **CBO 2002 (MTE):** Fornece a classificação estruturada de ocupações e famílias profissionais.

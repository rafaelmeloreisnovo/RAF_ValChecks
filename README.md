# RAF_ValChecks
Workflow topology QL validação de gates e recipsts e proveniency ♥φ — Homeostase energética como objetivo de engenharia: executar o mínimo suficiente para obter a evidência necessária, sem reduzir a segurança nem trocar verificação por suposição.


epistemic_status: VERIFIED_LIMITED
claim_allowed: false

artifacts_written:
  - repository: rafaelmeloreisnovo/RAF_ValChecks
    branch: raf-valchecks-core-v1
    files:
      - schemas/validation-manifest.schema.json
      - schemas/receipt.schema.json
      - action.yml
      - bin/raf-valcheck.sh
      - examples/validation.yml
    commits:
      - 85105aabfb092d2376f0307105e82f8f4e7226a2
      - e8d998e5cc8972af1df34d349f9192d642abacf5
      - f63ff03346a9c174f844a19671ce4c2d368c797d
      - ac7c2f2f34deb5593be13a7f2f497816a3df4c71
      - 20580ea9af3330c7a0458f888e33c04b76cf88d5

  - github_pull_request:
      repository: rafaelmeloreisnovo/RAF_ValChecks
      number: 1
      state: OPEN
      draft: true
      head: 20580ea9af3330c7a0458f888e33c04b76cf88d5
      base: 846916e51481a40d3d6b060eb7a6f13e6a1e5481

executions:
  - GitHub repository metadata inspection
  - GitHub repository content search
  - GitHub branch creation
  - GitHub file creation
  - GitHub pull request creation
  - GitHub exact-branch file readback
  - Google Drive search for CURRENT_STATE and canonical pointers
  - Supabase read-only schema inspection
  - Supabase read-only table and column inspection
  - Notion search for canonical RAFAELIA pages
  - AlphaXiv literature search
  - Undermind orientation and workspace discovery

sources_read:
  github:
    - rafaelmeloreisnovo/RAF_ValChecks
  drive:
    - RAFAELIA — CURRENT_STATE Ω — HOTSTATE V4.5
  notion:
    - RAFAELIA Ω — Retomada auditável START HERE
    - RAFAELIA — Rotas canônicas e autoridades
    - μRECEIPT — GitHub gates × B0160 provenance
    - Agent Operating Guide — RAFCODEΦ Π Ω
  supabase:
    - raf_private.novoexport_formula_observations_v1
    - raf_private.omega_ingest_receipts_v1
    - raf_private.omega_continuity_events_v1
    - raf_private.omega_typed_tokens_v1
    - raf_private.omega_void_catalog_v1
    - raf_private.omega_forest_route_matrix_v1
    - raf_private.mapa_cross_source_edges_v1
    - raf_private.global_writer_leases_v1
    - raf_private.github_file_observations_v1
  alphaxiv:
    - reproducible-builds
    - lockfiles
    - artifact verifiability
    - software supply-chain provenance
  undermind:
    workspace: RAFAELIA Ω — Sementes multidimensionais

hashes_verified:
  github:
    - README blob:
        sha: c25cb6e00a8a5d5f6e33ed8160a42ab71af9ae40
    - action.yml:
        sha: d6a74ec8ff9ce02980f31682055900f314b40ea5
    - bin/raf-valcheck.sh:
        sha: 2044eda4f3d1b0d7bcc26e072bf502a874e0b6e1
    - receipt.schema.json:
        sha: 086bc7ede66f13fdcab7c83e601abc807975d0cb

  database:
    - schema and metadata observed
    - source byte hashes of the 400 formulas not confirmed

falsifiers_tested:
  - repository implementation absence detected
  - empty GitHub code search result detected
  - manifest missing path condition represented
  - receipt missing path condition represented
  - source commit not pinned condition represented
  - update policy undeclared condition represented
  - unsupported manifest format condition represented
  - claim_allowed forced to false in receipt schema
  - Supabase public schema absence checked
  - private raf_private schema presence checked

falsifiers_not_yet_executed:
  - actual Action run in a consumer repository
  - malformed manifest execution
  - invalid commit execution
  - receipt hash mismatch
  - predecessor mismatch
  - receipt expiration
  - rollback execution
  - signature verification
  - artifact retention verification
  - topological graph consistency
  - Invariante das Invariantes evaluation

F_ok:
  - intenção arquitetural compreendida
  - método e gates definidos
  - repositório RAF_ValChecks identificado
  - primeiro núcleo materializado em branch isolada
  - contrato de manifesto criado
  - contrato de receipt criado
  - entrada de Action criada
  - leitura de volta confirmada
  - PR draft criado sem merge
  - fontes Drive, Supabase, Notion, AlphaXiv e Undermind localizadas

F_gap:
  - Invariante das Invariantes ainda não localizada como artefato canônico
  - grafo computável ainda não executado
  - 400 fórmulas ainda não reconciliadas
  - receipts reais ainda não consumidos pelo Action
  - assinaturas ainda não verificadas
  - retenção GitHub de 90 dias ainda não executada
  - falsificadores ainda não rodados em CI
  - integração Drive/Supabase/Notion ainda não persistida como novo receipt
  - nenhum PASS global autorizado

F_next:
  - localizar o artefato canônico da Invariante das Invariantes
  - executar o Action em um consumidor controlado com manifesto inválido e válido
  - criar o primeiro receipt de execução com predecessor, falsificadores, rollback e escopo de impacto

rollback:
  repository: rafaelmeloreisnovo/RAF_ValChecks
  action: fechar PR draft #1 ou remover a branch raf-valchecks-core-v1
  main_changed: false

energy_policy:
  principle: HOMEOSTASE_ENERGETICA
  reuse_valid_receipts: true
  recompute_scope: IMPACT_CONE_ONLY
  update_policy: OBSERVE_ONLY
